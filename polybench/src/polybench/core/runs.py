"""Planning, starting, executing and reading back benchmark runs."""

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlmodel import Session, col, func, select

from polybench.core.providers import check_provider, make_provider
from polybench.core.tasks import select_tasks
from polybench.db import get_session
from polybench.engine import RunConfig, config_from_run, create_run, run_benchmark
from polybench.models import BenchmarkRun, Sample, TaskResult
from polybench.providers.base import LLMProvider
from polybench.sandbox.images import docker_available, ensure_images
from polybench.sandbox.runner import SandboxRunner
from polybench.schemas import Difficulty, Task

_log = logging.getLogger("polybench.core.runs")

ACTIVE_STATUSES = ("PENDING", "RUNNING")


class NoTasksError(ValueError):
    def __init__(self) -> None:
        super().__init__("No tasks match the given filters.")


@dataclass
class RunPlan:
    """Everything needed to start a run, checked up front."""

    cfg: RunConfig
    tasks: list[Task]
    provider: LLMProvider


def preview_run(
    *,
    provider: str,
    tasks_dir: str | Path,
    lang: str | None = None,
    difficulty: Difficulty | str | None = None,
    tags: list[str] | None = None,
) -> list[Task]:
    """The tasks a run would cover, checking the provider without connecting to it.

    Raises ProviderError for an unknown or unconfigured provider, then
    NoTasksError if the filters leave nothing to run.
    """
    check_provider(provider)
    tasks = select_tasks(tasks_dir, lang=lang, difficulty=difficulty, tags=tags)
    if not tasks:
        raise NoTasksError()
    return tasks


def plan_run(
    *,
    provider: str,
    model: str,
    tasks_dir: str | Path,
    samples: int = 5,
    k: int = 1,
    temperature: float = 0.2,
    lang: str | None = None,
    difficulty: Difficulty | str | None = None,
    tags: list[str] | None = None,
) -> RunPlan:
    """Validate a run request as preview_run does, then build its provider."""
    tasks = preview_run(
        provider=provider,
        tasks_dir=tasks_dir,
        lang=lang,
        difficulty=difficulty,
        tags=tags,
    )
    llm = make_provider(provider, model, temperature)
    cfg = RunConfig(model, provider, samples, k, temperature, lang or None, tags)
    return RunPlan(cfg, tasks, llm)


def active_run_count(session: Session) -> int:
    stmt = (
        select(func.count())
        .select_from(BenchmarkRun)
        .where(col(BenchmarkRun.status).in_(ACTIVE_STATUSES))
    )
    return session.exec(stmt).one()


def start_run(session: Session, plan: RunPlan) -> BenchmarkRun:
    """Record the run as PENDING. The caller then executes it, in the foreground
    with run_benchmark or in the background with execute_run."""
    return create_run(session, plan.cfg, plan.tasks)


def execute_run(run_id: str, plan: RunPlan) -> None:
    """Execute a recorded run in its own DB session, for use off the request thread.

    Builds any missing sandbox image first, so a fresh deployment works without
    `polybench setup`. If the run already has samples (it was interrupted), only
    the missing ones are generated. Never raises: a failure is logged and the run
    is marked FAILED.
    """
    try:
        if not docker_available():
            raise RuntimeError("Docker is not available.")
        ensure_images(_log.info)
        with get_session() as session:
            _log.info(
                "Starting run %s: %s via %s", run_id, plan.cfg.model, plan.cfg.provider
            )
            run_benchmark(
                run_id, plan.cfg, plan.tasks, plan.provider, SandboxRunner(), session
            )
            _log.info("Run %s completed", run_id)
    except Exception as exc:
        _log.error("Run %s failed: %s", run_id, exc, exc_info=True)
        with get_session() as session:
            run = session.get(BenchmarkRun, run_id)
            if run is not None:
                run.status = "FAILED"
                session.add(run)
                session.commit()


def resume_plan(run: BenchmarkRun, tasks_dir: str | Path) -> RunPlan:
    """The plan to finish a stored run: its original settings, task filters and
    provider. Raises ProviderError or NoTasksError like plan_run."""
    cfg = config_from_run(run)
    tasks = preview_run(
        provider=cfg.provider, tasks_dir=tasks_dir, lang=cfg.lang, tags=cfg.tags
    )
    return RunPlan(cfg, tasks, make_provider(cfg.provider, cfg.model, cfg.temperature))


def _resume_all(run_ids: list[str], tasks_dir: str | Path) -> None:
    for run_id in run_ids:
        with get_session() as session:
            run = session.get(BenchmarkRun, run_id)
            if run is None:
                continue
            try:
                plan = resume_plan(run, tasks_dir)
            except Exception as exc:
                _log.warning("Can't resume run %s, marking it FAILED: %s", run_id, exc)
                run.status = "FAILED"
                session.add(run)
                session.commit()
                continue
        _log.info("Resuming interrupted run %s (%s)", run_id, plan.cfg.model)
        execute_run(run_id, plan)


def handle_interrupted_runs(tasks_dir: str | Path, *, resume: bool) -> int:
    """Deal with runs a previous process left PENDING or RUNNING.

    With resume=True they're finished one after another in a background thread,
    keeping the samples they already have; otherwise they're marked FAILED.
    Returns how many runs were found.
    """
    with get_session() as session:
        if not resume:
            return mark_orphaned_runs_failed(session)
        run_ids = [
            r.id
            for r in session.exec(
                select(BenchmarkRun).where(
                    col(BenchmarkRun.status).in_(ACTIVE_STATUSES)
                )
            ).all()
        ]
    if run_ids:
        threading.Thread(
            target=_resume_all, args=(run_ids, tasks_dir), daemon=True
        ).start()
    return len(run_ids)


def mark_orphaned_runs_failed(session: Session) -> int:
    """Fail runs left PENDING or RUNNING by a process that has since exited."""
    orphans = session.exec(
        select(BenchmarkRun).where(col(BenchmarkRun.status).in_(ACTIVE_STATUSES))
    ).all()
    for run in orphans:
        run.status = "FAILED"
        session.add(run)
    if orphans:
        session.commit()
    return len(orphans)


def list_runs(
    session: Session,
    limit: int = 20,
    offset: int = 0,
    provider: str | None = None,
    lang: str | None = None,
) -> list[BenchmarkRun]:
    """Runs, newest first."""
    stmt = select(BenchmarkRun)
    if provider:
        stmt = stmt.where(BenchmarkRun.provider == provider)
    if lang:
        stmt = stmt.where(BenchmarkRun.language_filter == lang)
    stmt = (
        stmt.order_by(col(BenchmarkRun.created_at).desc()).offset(offset).limit(limit)
    )
    return list(session.exec(stmt).all())


def task_scores(
    session: Session, run_ids: list[str]
) -> dict[str, list[dict[str, Any]]]:
    """Per-task pass@k for several runs in one query, without their samples.

    Each run maps to its tasks in task-ID order, as
    {"task_id", "pass_at_k", "samples_done"}.
    """
    scores: dict[str, list[dict[str, Any]]] = {run_id: [] for run_id in run_ids}
    if not run_ids:
        return scores
    rows = session.exec(
        select(TaskResult)
        .where(col(TaskResult.run_id).in_(run_ids))
        .order_by(col(TaskResult.task_id))
    ).all()
    for r in rows:
        scores[r.run_id].append(
            {
                "task_id": r.task_id,
                "pass_at_k": r.task_pass_at_k,
                "samples_done": r.samples_generated,
            }
        )
    return scores


def task_history(session: Session, task_id: str) -> dict[str, Any]:
    """How one task has scored across runs, newest run first, plus how its
    failed samples broke down by failure kind over all those runs."""
    rows = session.exec(
        select(TaskResult, BenchmarkRun)
        .join(BenchmarkRun, col(BenchmarkRun.id) == col(TaskResult.run_id))
        .where(TaskResult.task_id == task_id)
        .order_by(col(BenchmarkRun.created_at).desc())
    ).all()
    runs = [
        {
            "run_id": run.id,
            "model": run.model,
            "provider": run.provider,
            "status": run.status,
            "created_at": run.created_at.isoformat(),
            "k": run.k,
            "samples_done": tr.samples_generated,
            "samples_passed": tr.samples_passed,
            "pass_at_k": tr.task_pass_at_k,
        }
        for tr, run in rows
    ]
    failures: dict[str, int] = {}
    result_ids = [tr.id for tr, _ in rows]
    if result_ids:
        kinds = session.exec(
            select(Sample.failure_kind, func.count())
            .where(col(Sample.task_result_id).in_(result_ids))
            .where(col(Sample.passed).is_(False))
            .group_by(col(Sample.failure_kind))
        ).all()
        failures = {kind or "unknown": count for kind, count in kinds}
    return {"task_id": task_id, "runs": runs, "failures": failures}


def task_results(session: Session, run_id: str) -> list[TaskResult]:
    stmt = (
        select(TaskResult)
        .where(TaskResult.run_id == run_id)
        .order_by(col(TaskResult.task_id))
    )
    return list(session.exec(stmt).all())


def run_samples(session: Session, run_id: str) -> list[Sample]:
    stmt = select(Sample).join(TaskResult).where(TaskResult.run_id == run_id)
    return list(session.exec(stmt).all())
