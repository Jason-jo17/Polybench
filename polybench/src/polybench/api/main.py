import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import os
from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlmodel import select

from polybench.api.deps import SessionDep, verify_password
from polybench.compare import compare_runs
from polybench.config import settings
from polybench.core import providers as core_providers
from polybench.core import runs as core_runs
from polybench.core.tasks import find_task, parse_tags, public_task, select_tasks
from polybench.db import init_db
from polybench.models import BenchmarkRun, TaskResult

_TASKS_DEFAULT = Path(settings.polybench_tasks_dir).resolve()


def _handle_interrupted_runs() -> None:
    """Resume (or, with POLYBENCH_RESUME_RUNS=false, fail) runs a previous server
    process left unfinished."""
    count = core_runs.handle_interrupted_runs(
        _TASKS_DEFAULT, resume=settings.polybench_resume_runs
    )
    if count:
        action = "Resuming" if settings.polybench_resume_runs else "Marked FAILED:"
        logging.info("%s %d interrupted run(s).", action, count)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    _handle_interrupted_runs()
    yield


app = FastAPI(
    title="PolyBench API", dependencies=[Depends(verify_password)], lifespan=lifespan
)

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


class RunRequest(BaseModel):
    model: str = settings.polybench_default_model
    provider: str = "anthropic"
    samples: int = 5
    k: int = 1
    temperature: float = 0.2
    lang: str | None = None
    tags: str | None = None


@app.post("/api/runs")
def start_run(
    req: RunRequest, background_tasks: BackgroundTasks, session: SessionDep
) -> dict[str, str]:
    limit = settings.polybench_max_concurrent_runs
    if core_runs.active_run_count(session) >= limit:
        raise HTTPException(
            status_code=429, detail=f"Maximum concurrent runs ({limit}) reached."
        )

    try:
        plan = core_runs.plan_run(
            provider=req.provider,
            model=req.model,
            tasks_dir=_TASKS_DEFAULT,
            samples=req.samples,
            k=req.k,
            temperature=req.temperature,
            lang=req.lang,
            tags=parse_tags(req.tags),
        )
    except core_runs.NoTasksError:
        raise HTTPException(
            status_code=400, detail="No tasks match the chosen language and tags."
        )
    except core_providers.ProviderError as e:
        raise HTTPException(status_code=400, detail=str(e))

    run_record = core_runs.start_run(session, plan)
    background_tasks.add_task(core_runs.execute_run, run_record.id, plan)
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
    include: str | None = Query(
        default=None,
        description="`task_scores` adds each run's per-task pass@k (no samples).",
    ),
) -> list[dict[str, Any]]:
    runs = core_runs.list_runs(session, limit=limit, offset=offset)
    rows = [run.model_dump(mode="json") for run in runs]
    if include == "task_scores":
        scores = core_runs.task_scores(session, [run.id for run in runs])
        for row in rows:
            row["task_scores"] = scores[row["id"]]
    elif include is not None:
        raise HTTPException(status_code=400, detail="include must be task_scores")
    return rows


@app.get("/api/runs/compare")
def compare_runs_api(
    run_a: str, run_b: str, session: SessionDep
) -> list[dict[str, Any]]:
    """Per-task pass@k for two runs. A task only one run included has null for
    the other run and for delta."""
    return [row.to_dict() for row in compare_runs(session, run_a, run_b)]


@app.get("/api/runs/{run_id}/results")
def get_run_results(run_id: str, session: SessionDep) -> dict[str, Any]:
    run = session.get(BenchmarkRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "run": run,
        "results": core_runs.task_results(session, run_id),
        "samples": core_runs.run_samples(session, run_id),
    }


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
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/providers")
def list_providers() -> dict[str, list[str]]:
    """Providers that can be used right now."""
    return {
        "providers": [
            p for p in core_providers.ALL_PROVIDERS if core_providers.is_configured(p)
        ]
    }


@app.get("/api/tasks")
def list_tasks(
    lang: str | None = None,
    difficulty: str | None = None,
) -> list[dict[str, Any]]:
    try:
        tasks = select_tasks(_TASKS_DEFAULT, lang=lang, difficulty=difficulty)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return [public_task(t) for t in tasks]


@app.get("/api/tasks/{task_id:path}")
def get_task(task_id: str) -> dict[str, Any]:
    """Fetch a single task by its ID (e.g. python/lru_cache)."""
    task = find_task(_TASKS_DEFAULT, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return public_task(task)


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
    status = {
        p: {
            "configured": core_providers.is_configured(p),
            "requires_key": p in core_providers.CLOUD_PROVIDERS,
        }
        for p in core_providers.ALL_PROVIDERS
    }
    return {"providers": status}
