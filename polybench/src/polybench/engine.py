import concurrent.futures
import logging
import threading
from sqlmodel import Session
from rich.progress import Progress

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
    run_record = session.get(BenchmarkRun, run_id)
    if not run_record:
        _log.error(f"BenchmarkRun {run_id} not found in DB")
        return None

    run_record.status = "RUNNING"
    session.add(run_record)
    session.commit()

    tasks = sorted(tasks, key=lambda t: t.id)

    # Pre-create TaskResult rows so we have IDs before spawning workers.
    task_result_ids: dict[str, str] = {}
    for task in tasks:
        sandbox_image, sandbox_test_cmd = _resolve_sandbox_spec(task)
        tr = TaskResult(
            run_id=run_record.id,
            task_id=task.id,
            language=task.language,
            difficulty=task.difficulty.value,
            samples_generated=cfg.n,
            samples_passed=0,
            task_pass_at_k=0.0,
            sandbox_image=sandbox_image,
            sandbox_test_cmd=sandbox_test_cmd,
        )
        session.add(tr)
        session.commit()
        task_result_ids[task.id] = tr.id

    # In-memory pass counters — avoids a DB read per sample inside the lock.
    pass_counts: dict[str, int] = {task.id: 0 for task in tasks}
    db_lock = threading.Lock()

    jobs = [(task, i, task_result_ids[task.id]) for task in tasks for i in range(cfg.n)]

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
                    failure = classify(run_res.exit_code, run_res.stdout, run_res.stderr, run_res.timed_out)
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
                    task.id, sample_index, exc, exc_info=True,
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
                session.commit()
                if passed:
                    pass_counts[task.id] += 1
                progress.advance(bar)

        max_workers = min(8, len(jobs)) if jobs else 1
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(worker, t, i, tr_id) for t, i, tr_id in jobs]
            for future in concurrent.futures.as_completed(futures):
                # Worker handles its own exceptions; re-raise only truly unexpected ones.
                try:
                    future.result()
                except Exception as exc:
                    _log.error("Unhandled future exception: %s", exc, exc_info=True)

    # Write final pass counts and pass@k in a single pass over tasks.
    total_pass_at_k = 0.0
    for task in tasks:
        result_row: TaskResult | None = session.get(TaskResult, task_result_ids[task.id])
        if result_row is not None:
            result_row.samples_passed = pass_counts[task.id]
            result_row.task_pass_at_k = pass_at_k(cfg.n, pass_counts[task.id], cfg.k)
            session.add(result_row)
            total_pass_at_k += result_row.task_pass_at_k

    if tasks:
        run_record.pass_at_k = total_pass_at_k / len(tasks)
    run_record.status = "COMPLETED"
    session.add(run_record)
    session.commit()

    return run_record
