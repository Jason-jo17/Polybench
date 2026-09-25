from polybench.compare import compare_runs
from polybench.db import get_session
from polybench.models import BenchmarkRun, TaskResult


def _run(session, scores: dict[str, float]) -> str:
    run = BenchmarkRun(
        model="m",
        provider="mock",
        samples_per_task=1,
        k=1,
        temperature=0.2,
        total_tasks=len(scores),
        pass_at_k=0.0,
        status="COMPLETED",
    )
    session.add(run)
    session.commit()
    for task_id, score in scores.items():
        session.add(
            TaskResult(
                run_id=run.id,
                task_id=task_id,
                language=task_id.split("/")[0],
                difficulty="easy",
                samples_generated=1,
                samples_passed=int(score),
                task_pass_at_k=score,
            )
        )
    session.commit()
    return run.id


def test_tasks_in_only_one_run_are_not_scored_as_zero(tmp_db):
    with get_session() as session:
        python_only = _run(session, {"python/a": 1.0, "python/b": 0.0})
        everything = _run(session, {"python/a": 0.0, "python/b": 1.0, "go/c": 1.0})
        rows = {r.task_id: r for r in compare_runs(session, python_only, everything)}

    assert (rows["python/a"].run_a, rows["python/a"].run_b, rows["python/a"].delta) == (
        1.0,
        0.0,
        -1.0,
    )
    assert rows["python/b"].delta == 1.0
    # Only the second run included go/c: no score for A, and no change to report.
    assert rows["go/c"].run_a is None
    assert rows["go/c"].run_b == 1.0
    assert rows["go/c"].delta is None


def test_rows_are_sorted_by_task_id(tmp_db):
    with get_session() as session:
        a = _run(session, {"z/1": 1.0, "a/1": 1.0})
        b = _run(session, {"m/1": 1.0})
        assert [r.task_id for r in compare_runs(session, a, b)] == ["a/1", "m/1", "z/1"]
