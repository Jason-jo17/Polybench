import logging
from pathlib import Path

from polybench.config import settings
from polybench.db import get_session
from polybench.engine import run_benchmark, RunConfig
from polybench.providers.base import LLMProvider
from polybench.sandbox.runner import SandboxRunner
from polybench.tasks.loader import load_tasks
from polybench.tasks.registry import TaskRegistry

_log = logging.getLogger("polybench.api.worker")


def execute_benchmark_run(
    run_id: str, cfg: RunConfig, provider: LLMProvider, tasks_dir: Path | None = None
) -> None:
    if tasks_dir is None:
        tasks_dir = Path(settings.polybench_tasks_dir).resolve()
    """
    Background worker function to execute a benchmark run.
    This creates its own DB session so it can run independently of the HTTP request.
    """
    try:
        loaded = list(load_tasks(tasks_dir))
        registry = TaskRegistry(loaded)
        filtered = registry.filter(lang=cfg.lang, tags=cfg.tags)
        if not filtered:
            _log.warning("No tasks match the given filters for run.")
            with get_session() as session:
                from polybench.models import BenchmarkRun

                run_record = session.get(BenchmarkRun, run_id)
                if run_record:
                    run_record.status = "COMPLETED"
                    session.add(run_record)
                    session.commit()
            return

        runner = SandboxRunner()
        with get_session() as session:
            _log.info(
                f"Starting background run {run_id} for {cfg.model} via {cfg.provider}"
            )
            run_benchmark(run_id, cfg, filtered, provider, runner, session)
            _log.info("Background run completed.")
    except Exception as e:
        _log.error(f"Error in background worker: {e}", exc_info=True)
        with get_session() as session:
            from polybench.models import BenchmarkRun

            run_record = session.get(BenchmarkRun, run_id)
            if run_record:
                run_record.status = "FAILED"
                session.add(run_record)
                session.commit()
