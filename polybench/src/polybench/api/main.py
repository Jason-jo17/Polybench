import logging
from pathlib import Path
from typing import Any

import os
from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlmodel import select

from polybench.api.deps import SessionDep, verify_password
from polybench.api.worker import execute_benchmark_run
from polybench.config import settings
from polybench.db import init_db
from polybench.engine import RunConfig, create_run
from polybench.models import BenchmarkRun, TaskResult, Sample
from polybench.providers.anthropic_provider import AnthropicProvider
from polybench.providers.mock_provider import MockProvider
from polybench.providers.openai_compatible import OpenAICompatibleProvider
from polybench.tasks.loader import load_tasks
from polybench.tasks.registry import TaskRegistry

_TASKS_DEFAULT = Path(settings.polybench_tasks_dir).resolve()

# Using the same compat URLs as the CLI
_COMPAT_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "mistral": "https://api.mistral.ai/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "xai": "https://api.x.ai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "perplexity": "https://api.perplexity.ai",
}


def _make_provider(provider: str, model: str, temperature: float):
    if provider == "anthropic":
        return AnthropicProvider(model=model, temperature=temperature)
    if provider == "mock":
        return MockProvider(model=model, temperature=temperature)
    if provider == "ollama":
        return OpenAICompatibleProvider(
            api_key="ollama",
            base_url=settings.ollama_base_url,
            model=model,
            temperature=temperature,
        )
    if provider == "lmstudio":
        return OpenAICompatibleProvider(
            api_key="lm-studio",
            base_url=settings.lmstudio_base_url,
            model=model,
            temperature=temperature,
        )
    if provider in _COMPAT_BASE_URLS:
        api_key = getattr(settings, f"{provider}_api_key", None)
        if not api_key:
            raise ValueError(
                f"Missing API key for provider '{provider}'. Please set {provider.upper()}_API_KEY."
            )
        return OpenAICompatibleProvider(
            api_key=api_key,
            base_url=_COMPAT_BASE_URLS[provider],
            model=model,
            temperature=temperature,
        )
    raise ValueError(f"Unknown provider: {provider}")


app = FastAPI(title="PolyBench API", dependencies=[Depends(verify_password)])

# CORS Configuration
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
allowed_origins = [frontend_url] if frontend_url != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@app.on_event("startup")
def on_startup():
    init_db()

    # Cleanup orphaned runs from previous server instance
    from polybench.db import get_session

    with get_session() as session:
        orphans = session.exec(
            select(BenchmarkRun).where(BenchmarkRun.status.in_(["PENDING", "RUNNING"]))
        ).all()
        for run in orphans:
            run.status = "FAILED"
        if orphans:
            session.commit()
            logging.info(f"Marked {len(orphans)} orphaned runs as FAILED.")


class RunRequest(BaseModel):
    model: str = settings.polybench_default_model
    provider: str = "anthropic"
    samples: int = 5
    k: int = 1
    temperature: float = 0.2
    lang: str | None = None
    tags: str | None = None


@app.post("/api/runs")
def start_run(req: RunRequest, background_tasks: BackgroundTasks, session: SessionDep):
    active_runs = len(
        session.exec(
            select(BenchmarkRun).where(BenchmarkRun.status.in_(["PENDING", "RUNNING"]))
        ).all()
    )
    if active_runs >= settings.polybench_max_concurrent_runs:
        raise HTTPException(
            status_code=429,
            detail=f"Maximum concurrent runs ({settings.polybench_max_concurrent_runs}) reached.",
        )

    try:
        provider_impl = _make_provider(req.provider, req.model, req.temperature)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    tag_list = [t.strip() for t in req.tags.split(",")] if req.tags else None

    cfg = RunConfig(
        model=req.model,
        provider=req.provider,
        n=req.samples,
        k=req.k,
        temperature=req.temperature,
        lang=req.lang,
        tags=tag_list,
    )

    loaded = list(load_tasks(_TASKS_DEFAULT))
    registry = TaskRegistry(loaded)
    filtered = registry.filter(lang=cfg.lang, tags=cfg.tags)
    if not filtered:
        raise HTTPException(
            status_code=400,
            detail="No tasks match the chosen language and tags.",
        )

    run_record = create_run(session, cfg, filtered)

    background_tasks.add_task(
        execute_benchmark_run, run_record.id, cfg, provider_impl, _TASKS_DEFAULT
    )
    return {"message": "Run started in background", "run_id": run_record.id}


@app.get("/api/stats")
def get_stats(session: SessionDep) -> dict[str, Any]:
    runs = session.exec(select(BenchmarkRun)).all()
    total_runs = len(runs)
    completed = [r for r in runs if r.status == "COMPLETED"]
    providers_used = len(set(r.provider for r in runs))
    avg_pass_at_k = (
        sum(r.pass_at_k for r in completed if r.pass_at_k is not None) / len(completed)
        if completed
        else 0
    )
    # Most-used model
    model_counts: dict[str, int] = {}
    for r in runs:
        model_counts[r.model] = model_counts.get(r.model, 0) + 1
    most_used_model = (
        max(model_counts, key=lambda m: model_counts[m]) if model_counts else None
    )
    # Active runs
    active_runs = len([r for r in runs if r.status in ("PENDING", "RUNNING")])
    # Total tasks executed
    results = session.exec(select(TaskResult)).all()
    total_tasks_executed = len(results)
    return {
        "total_runs": total_runs,
        "completed_runs": len(completed),
        "active_runs": active_runs,
        "providers_used": providers_used,
        "avg_pass_at_k": avg_pass_at_k,
        "most_used_model": most_used_model,
        "total_tasks_executed": total_tasks_executed,
    }


@app.get("/api/runs")
def list_runs(
    session: SessionDep,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[BenchmarkRun]:
    stmt = (
        select(BenchmarkRun)
        .order_by(BenchmarkRun.created_at.desc())  # type: ignore
        .offset(offset)
        .limit(limit)
    )
    return session.exec(stmt).all()


@app.get("/api/runs/compare")
def compare_runs_api(
    run_a: str, run_b: str, session: SessionDep
) -> list[dict[str, Any]]:
    a_rows = session.exec(select(TaskResult).where(TaskResult.run_id == run_a)).all()
    b_rows = session.exec(select(TaskResult).where(TaskResult.run_id == run_b)).all()

    a_map = {r.task_id: r.task_pass_at_k for r in a_rows}
    b_map = {r.task_id: r.task_pass_at_k for r in b_rows}

    rows = []
    for task_id in sorted(set(a_map) | set(b_map)):
        rows.append(
            {
                "task_id": task_id,
                "run_a": a_map.get(task_id, 0.0),
                "run_b": b_map.get(task_id, 0.0),
            }
        )
    return rows


@app.get("/api/runs/{run_id}/results")
def get_run_results(run_id: str, session: SessionDep) -> dict[str, Any]:
    run = session.get(BenchmarkRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    results = session.exec(select(TaskResult).where(TaskResult.run_id == run_id)).all()
    samples = session.exec(
        select(Sample).join(TaskResult).where(TaskResult.run_id == run_id)
    ).all()
    return {"run": run, "results": results, "samples": samples}


@app.get("/api/runs/{run_id}/status")
def get_run_status(run_id: str, session: SessionDep) -> dict[str, Any]:
    run = session.get(BenchmarkRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "id": run.id,
        "status": run.status,
        "pass_at_k": run.pass_at_k,
    }


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


@app.get("/api/providers")
def list_providers():
    configured = ["mock", "ollama", "lmstudio", "anthropic"]
    for p in _COMPAT_BASE_URLS:
        if getattr(settings, f"{p}_api_key", None):
            configured.append(p)
    return {"providers": configured}


@app.get("/api/tasks")
def list_tasks(
    lang: str | None = None,
    difficulty: str | None = None,
) -> list[dict]:
    from polybench.schemas import Difficulty as DifficultyEnum

    loaded = list(load_tasks(_TASKS_DEFAULT))
    registry = TaskRegistry(loaded)
    diff_enum = DifficultyEnum(difficulty) if difficulty else None
    filtered = registry.filter(lang=lang, difficulty=diff_enum)
    return [
        {
            "id": t.id,
            "title": t.title,
            "language": t.language,
            "difficulty": t.difficulty.value,
            "tags": t.tags,
            "prompt": t.prompt,
            "signature": t.signature,
            "timeout_seconds": t.timeout_seconds,
        }
        for t in filtered
    ]


@app.get("/api/tasks/{task_id:path}")
def get_task(task_id: str) -> dict:
    """Fetch a single task by its ID (e.g. python/lru_cache)."""
    loaded = list(load_tasks(_TASKS_DEFAULT))
    for t in loaded:
        if t.id == task_id:
            return {
                "id": t.id,
                "title": t.title,
                "language": t.language,
                "difficulty": t.difficulty.value,
                "tags": t.tags,
                "prompt": t.prompt,
                "signature": t.signature,
                "timeout_seconds": t.timeout_seconds,
            }
    raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, session: SessionDep) -> BenchmarkRun:
    """Fetch a single BenchmarkRun by ID."""
    run = session.get(BenchmarkRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.get("/api/providers/status")
def providers_status() -> dict[str, Any]:
    """Report which providers have API keys configured."""
    status: dict[str, dict] = {}
    always_available = ["mock", "ollama", "lmstudio"]
    for p in always_available:
        status[p] = {"configured": True, "requires_key": False}
    for p in _COMPAT_BASE_URLS:
        key = getattr(settings, f"{p}_api_key", None)
        status[p] = {"configured": bool(key), "requires_key": True}
    status["anthropic"] = {
        "configured": bool(settings.anthropic_api_key),
        "requires_key": True,
    }
    return {"providers": status}
