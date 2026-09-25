"""Check that a task is sound: solvable, and not passable by an empty implementation."""

from dataclasses import dataclass

from polybench.sandbox.runner import SandboxResult, SandboxRunner
from polybench.schemas import Task
from polybench.scoring.taxonomy import classify

_OUTPUT_TAIL = 600


@dataclass(frozen=True)
class VerifyResult:
    task_id: str
    ok: bool
    problem: str | None = None
    output: str = ""


def _tail(res: SandboxResult) -> str:
    text = "\n".join(part for part in (res.stdout, res.stderr) if part).strip()
    return text[-_OUTPUT_TAIL:]


def verify_task(task: Task, runner: SandboxRunner) -> VerifyResult:
    """Run the task's reference solution and its bare signature through the sandbox.

    The reference must pass the hidden tests. The signature on its own (a stub with
    no real implementation) must fail them; if it passes, the tests can't tell a
    real solution from an empty one.
    """
    if not task.reference_solution:
        return VerifyResult(task.id, False, "no reference_solution in the task file")

    ref = runner.run(task.reference_solution, task)
    kind = classify(ref.exit_code, ref.stdout, ref.stderr, ref.timed_out)
    if kind is not None:
        return VerifyResult(
            task.id,
            False,
            f"reference solution fails the tests ({kind.value})",
            _tail(ref),
        )

    stub = runner.run(task.signature, task)
    if classify(stub.exit_code, stub.stdout, stub.stderr, stub.timed_out) is None:
        return VerifyResult(
            task.id,
            False,
            "the bare signature passes the tests, so they check too little",
        )

    return VerifyResult(task.id, True)
