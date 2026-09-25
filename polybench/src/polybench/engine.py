import concurrent.futures
import logging
import subprocess
import threading
from sqlmodel import Session, select
from rich.progress import Progress

from polybench.config import settings
from polybench.schemas import Task, Language
from polybench.models import BenchmarkRun, TaskResult, Sample
from polybench.providers.base import LLMProvider
from polybench.sandbox.runner import SandboxRunner
from polybench.sandbox.languages import SPECS
from polybench.extract import extract_code
from polybench.scoring.taxonomy import FailureKind, classify
from polybench.scoring.passk import pass_at_k

_log = logging.getLogger("polybench.engine")


class RunConfig:
    def __init__(
        self,
        model: str,
        provider: str,
        n: int,
        k: int,
        temperature: float,
        lang: str | None,
        tags: list[str] | None = None,
    ) -> None:
        self.model = model
        self.provider = provider
        self.n = n
        self.k = k
        self.temperature = temperature
        self.lang = lang
        self.tags = tags


def current_git_sha() -> str | None:
    """Return the checked-out commit, or None outside a git checkout."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def create_run(session: Session, cfg: RunConfig, tasks: list[Task]) -> BenchmarkRun:
    """Insert a PENDING BenchmarkRun for these tasks; run_benchmark executes it."""
    run = BenchmarkRun(
        model=cfg.model,
        provider=cfg.provider,
        language_filter=cfg.lang or None,
        samples_per_task=cfg.n,
        k=cfg.k,
        temperature=cfg.temperature,
        total_tasks=len(tasks),
        pass_at_k=0.0,
        status="PENDING",
        git_sha=current_git_sha(),
        tag_filter=",".join(cfg.tags) if cfg.tags else None,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def config_from_run(run: BenchmarkRun) -> RunConfig:
    """Rebuild the RunConfig a stored run was started with, e.g. to resume it."""
    return RunConfig(
        model=run.model,
        provider=run.provider,
        n=run.samples_per_task,
        k=run.k,
        temperature=run.temperature,
        lang=run.language_filter,
        tags=[t for t in (run.tag_filter or "").split(",") if t] or None,
    )


def _resolve_sandbox_spec(task: Task) -> tuple[str | None, str | None]:
    """Return (image, space-joined test_cmd) for a task, or (None, None)."""
    if task.image and task.test_cmd:
        return task.image, " ".join(task.test_cmd)
    try:
        spec = SPECS[Language(task.language)]
        return spec.image, " ".join(spec.test_cmd)
    except (ValueError, KeyError):
        return None, None


def run_benchmark(
    run_id: str,
    cfg: RunConfig,
    tasks: list[Task],
    provider: LLMProvider,
    runner: SandboxRunner,
    session: Session,
) -> BenchmarkRun | None:
    """Execute a run, or finish one that was interrupted.

    Samples already stored for this run are kept and skipped, so calling this
    again after a crash or restart only does the remaining work. Each task's
    scores are updated as its samples finish, so a run in progress shows real
    partial results.
    """
    run_record = session.get(BenchmarkRun, run_id)
    if not run_record:
        _log.error(f"BenchmarkRun {run_id} not found in DB")
        return None

    run_record.status = "RUNNING"
    session.add(run_record)
    session.commit()

    tasks = sorted(tasks, key=lambda t: t.id)
    existing = {
        tr.task_id: tr
        for tr in session.exec(select(TaskResult).where(TaskResult.run_id == run_id))
    }

    # One TaskResult per task, created up front so workers have its ID.
    task_result_ids: dict[str, str] = {}
    done: dict[str, set[int]] = {}
    pass_counts: dict[str, int] = {}
    for task in tasks:
        tr = existing.get(task.id)
        if tr is None:
            sandbox_image, sandbox_test_cmd = _resolve_sandbox_spec(task)
            tr = TaskResult(
                run_id=run_record.id,
                task_id=task.id,
                language=task.language,
                difficulty=task.difficulty.value,
                samples_generated=0,
                samples_passed=0,
                task_pass_at_k=0.0,
                sandbox_image=sandbox_image,
                sandbox_test_cmd=sandbox_test_cmd,
            )
            session.add(tr)
            session.commit()
        task_result_ids[task.id] = tr.id
        stored = session.exec(
            select(Sample).where(Sample.task_result_id == tr.id)
        ).all()
        done[task.id] = {smp.sample_index for smp in stored}
        pass_counts[task.id] = sum(1 for smp in stored if smp.passed)

    db_lock = threading.Lock()
    jobs = [
        (task, i, task_result_ids[task.id])
        for task in tasks
        for i in range(cfg.n)
        if i not in done[task.id]
    ]
    if len(jobs) < len(tasks) * cfg.n:
        _log.info(
            "Resuming run %s: %d of %d samples left",
            run_id,
            len(jobs),
            len(tasks) * cfg.n,
        )

    def record_progress(task: Task) -> None:
        """Write the task's scores so far and the run's running average (holds db_lock)."""
        tr = session.get(TaskResult, task_result_ids[task.id])
        if tr is not None:
            tr.samples_generated = len(done[task.id])
            tr.samples_passed = pass_counts[task.id]
            tr.task_pass_at_k = _task_score(
                len(done[task.id]), pass_counts[task.id], cfg.k
            )
            session.add(tr)
        started = [t for t in tasks if done[t.id]]
        if started and run_record is not None:
            run_record.pass_at_k = sum(
                _task_score(len(done[t.id]), pass_counts[t.id], cfg.k) for t in started
            ) / len(started)
            session.add(run_record)
        session.commit()

    with Progress() as progress:
        bar = progress.add_task("[cyan]Running benchmark...", total=len(jobs))

        def worker(task: Task, sample_index: int, task_result_id: str) -> None:
            raw_output = ""
            extracted_code: str | None = None
            passed = False
            failure_kind: str | None = FailureKind.RUNTIME_ERROR.value
            exit_code: int | None = None
            stdout = ""
            stderr = ""
            runtime_ms = 0
            timed_out = False
            input_tokens: int | None = None
            output_tokens: int | None = None

            try:
                prompt = (
                    f"Language: {task.language}\n"
                    f"Required signature:\n{task.signature}\n\n"
                    f"Task:\n{task.prompt}"
                )
                gen_res = provider.generate(prompt)
                raw_output = gen_res.raw_output
                runtime_ms = gen_res.runtime_ms
                input_tokens = gen_res.input_tokens
                output_tokens = gen_res.output_tokens

                extracted_code = extract_code(raw_output, task.language)

                if not extracted_code:
                    failure_kind = FailureKind.EXTRACTION_FAILED.value
                else:
                    run_res = runner.run(extracted_code, task)
                    failure = classify(
                        run_res.exit_code,
                        run_res.stdout,
                        run_res.stderr,
                        run_res.timed_out,
                    )
                    passed = failure is None
                    failure_kind = failure.value if failure else None
                    exit_code = run_res.exit_code
                    stdout = run_res.stdout
                    stderr = run_res.stderr
                    runtime_ms = run_res.runtime_ms
                    timed_out = run_res.timed_out

            except Exception as exc:
                _log.error(
                    "Worker exception task=%s sample=%d: %s",
                    task.id,
                    sample_index,
                    exc,
                    exc_info=True,
                )
                failure_kind = FailureKind.RUNTIME_ERROR.value

            with db_lock:
                sample = Sample(
                    task_result_id=task_result_id,
                    sample_index=sample_index,
                    raw_output=raw_output,
                    extracted_code=extracted_code,
                    passed=passed,
                    failure_kind=failure_kind,
                    exit_code=exit_code,
                    stdout=stdout,
                    stderr=stderr,
                    runtime_ms=runtime_ms,
                    timed_out=timed_out,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
                session.add(sample)
                done[task.id].add(sample_index)
                if passed:
                    pass_counts[task.id] += 1
                record_progress(task)
                progress.advance(bar)

        max_workers = max(1, min(settings.polybench_sandbox_workers, len(jobs)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(worker, t, i, tr_id) for t, i, tr_id in jobs]
            for future in concurrent.futures.as_completed(futures):
                # Worker handles its own exceptions; re-raise only truly unexpected ones.
                try:
                    future.result()
                except Exception as exc:
                    _log.error("Unhandled future exception: %s", exc, exc_info=True)

    # Final scores over every task, including samples from before a resume.
    total_pass_at_k = 0.0
    for task in tasks:
        result_row = session.get(TaskResult, task_result_ids[task.id])
        if result_row is not None:
            result_row.samples_generated = len(done[task.id])
            result_row.samples_passed = pass_counts[task.id]
            result_row.task_pass_at_k = _task_score(
                len(done[task.id]), pass_counts[task.id], cfg.k
            )
            session.add(result_row)
            total_pass_at_k += result_row.task_pass_at_k

    if tasks:
        run_record.pass_at_k = total_pass_at_k / len(tasks)
    run_record.status = "COMPLETED"
    session.add(run_record)
    session.commit()

    return run_record


def _task_score(samples_done: int, passed: int, k: int) -> float:
    """pass@k over the samples finished so far (k is capped at that count)."""
    if samples_done == 0:
        return 0.0
    return pass_at_k(samples_done, passed, min(k, samples_done))
