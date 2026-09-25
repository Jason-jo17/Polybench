"""Task-by-task comparison of two runs, shared by the API, CLI and MCP server."""

from dataclasses import asdict, dataclass
from typing import Any

from sqlmodel import Session, select

from polybench.models import TaskResult


@dataclass(frozen=True)
class TaskComparison:
    task_id: str
    run_a: float | None  # None: the task wasn't part of run A
    run_b: float | None
    delta: float | None  # run_b - run_a; None unless both runs include the task

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compare_runs(session: Session, run_a: str, run_b: str) -> list[TaskComparison]:
    """Per-task pass@k for two runs, over every task either run included.

    A task only one run included is reported with None for the other run rather
    than 0.0, so different task sets (e.g. different language filters) don't look
    like regressions or improvements.
    """
    a = _scores(session, run_a)
    b = _scores(session, run_b)
    rows = []
    for task_id in sorted(a.keys() | b.keys()):
        va, vb = a.get(task_id), b.get(task_id)
        delta = round(vb - va, 4) if va is not None and vb is not None else None
        rows.append(TaskComparison(task_id, va, vb, delta))
    return rows


def _scores(session: Session, run_id: str) -> dict[str, float]:
    results = session.exec(select(TaskResult).where(TaskResult.run_id == run_id)).all()
    return {r.task_id: r.task_pass_at_k for r in results}
