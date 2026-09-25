import pytest
from fastapi.testclient import TestClient

from polybench.config import settings


@pytest.fixture
def client(tmp_path, monkeypatch):
    """The API against a fresh SQLite database, with no dashboard password."""
    monkeypatch.setattr(settings, "polybench_db", str(tmp_path / "api.db"))
    monkeypatch.setattr(settings, "polybench_dashboard_password", None)
    from polybench.api.main import app

    with TestClient(app) as c:
        yield c


def test_task_list_never_exposes_hidden_fields(client):
    tasks = client.get("/api/tasks").json()
    assert len(tasks) >= 21
    for task in tasks:
        assert "test_code" not in task
        assert "reference_solution" not in task


def test_single_task_never_exposes_hidden_fields(client):
    task = client.get("/api/tasks/python/two_sum").json()
    assert task["id"] == "python/two_sum"
    assert "test_code" not in task
    assert "reference_solution" not in task


def test_unknown_task_is_404(client):
    assert client.get("/api/tasks/python/does_not_exist").status_code == 404


def test_run_with_no_matching_tasks_is_rejected(client):
    res = client.post(
        "/api/runs", json={"provider": "mock", "model": "demo", "tags": "no-such-tag"}
    )
    assert res.status_code == 400
    assert "No tasks match" in res.json()["detail"]


def test_password_protects_the_api_when_set(client, monkeypatch):
    monkeypatch.setattr(settings, "polybench_dashboard_password", "s3cret")
    assert client.get("/api/stats").status_code == 401
    assert client.get("/api/stats", auth=("anyone", "wrong")).status_code == 401
    assert client.get("/api/stats", auth=("anyone", "s3cret")).status_code == 200


def _add_runs(*models: str) -> list[str]:
    """Insert completed runs, oldest first, and return their IDs."""
    from datetime import datetime, timedelta

    from polybench.db import get_session
    from polybench.models import BenchmarkRun

    ids = []
    with get_session() as session:
        for i, model in enumerate(models):
            run = BenchmarkRun(
                model=model,
                provider="mock",
                samples_per_task=1,
                k=1,
                temperature=0.2,
                total_tasks=1,
                pass_at_k=0.5,
                status="COMPLETED",
                created_at=datetime(2026, 1, 1) + timedelta(hours=i),
            )
            session.add(run)
            session.commit()
            ids.append(run.id)
    return ids


def test_runs_are_listed_newest_first_with_paging(client):
    _add_runs("first", "second", "third")

    assert [r["model"] for r in client.get("/api/runs").json()] == [
        "third",
        "second",
        "first",
    ]
    page = client.get("/api/runs?limit=1&offset=1").json()
    assert [r["model"] for r in page] == ["second"]


def test_stats_count_runs(client):
    _add_runs("a", "b")
    stats = client.get("/api/stats").json()
    assert stats["total_runs"] == 2 and stats["completed_runs"] == 2
    assert stats["avg_pass_at_k"] == 0.5


def test_compare_reports_tasks_missing_from_one_run_as_null(client):
    from polybench.db import get_session
    from polybench.models import TaskResult

    a, b = _add_runs("a", "b")
    with get_session() as session:
        for run_id, task_id in [(a, "python/x"), (b, "python/x"), (b, "go/y")]:
            session.add(
                TaskResult(
                    run_id=run_id,
                    task_id=task_id,
                    language="python",
                    difficulty="easy",
                    samples_generated=1,
                    samples_passed=1,
                    task_pass_at_k=1.0,
                )
            )
        session.commit()

    rows = {
        r["task_id"]: r
        for r in client.get(f"/api/runs/compare?run_a={a}&run_b={b}").json()
    }
    assert rows["python/x"] == {
        "task_id": "python/x",
        "run_a": 1.0,
        "run_b": 1.0,
        "delta": 0.0,
    }
    assert rows["go/y"] == {
        "task_id": "go/y",
        "run_a": None,
        "run_b": 1.0,
        "delta": None,
    }


def test_run_with_unknown_provider_is_rejected(client):
    res = client.post("/api/runs", json={"provider": "nope", "model": "m"})
    assert res.status_code == 400
    assert "Unknown provider" in res.json()["detail"]


def test_run_with_missing_key_is_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    res = client.post("/api/runs", json={"provider": "anthropic", "model": "m"})
    assert res.status_code == 400
    assert "ANTHROPIC_API_KEY" in res.json()["detail"]


def test_task_list_with_unknown_difficulty_is_400(client):
    assert client.get("/api/tasks?difficulty=impossible").status_code == 400


def test_providers_reflect_configured_keys(client, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    monkeypatch.setattr(settings, "groq_api_key", "gsk-test")
    status = client.get("/api/providers/status").json()["providers"]
    assert status["anthropic"] == {"configured": False, "requires_key": True}
    assert status["groq"] == {"configured": True, "requires_key": True}
    assert status["mock"] == {"configured": True, "requires_key": False}
    listed = client.get("/api/providers").json()["providers"]
    assert "groq" in listed and "mock" in listed and "anthropic" not in listed


def test_runs_can_include_per_task_scores_without_samples(client):
    from polybench.db import get_session
    from polybench.models import Sample, TaskResult

    (run_id,) = _add_runs("a")
    with get_session() as session:
        for task_id, score, done in [
            ("python/b", 0.5, 2),
            ("go/a", 1.0, 1),
            ("rust/c", 0.0, 0),
        ]:
            tr = TaskResult(
                run_id=run_id,
                task_id=task_id,
                language=task_id.split("/")[0],
                difficulty="easy",
                samples_generated=done,
                samples_passed=int(score * done),
                task_pass_at_k=score,
            )
            session.add(tr)
            session.commit()
            session.add(
                Sample(
                    task_result_id=tr.id, sample_index=0, raw_output="x", passed=True
                )
            )
        session.commit()

    (run,) = client.get("/api/runs?include=task_scores").json()

    assert run["id"] == run_id
    assert run["task_scores"] == [
        {"task_id": "go/a", "pass_at_k": 1.0, "samples_done": 1},
        {"task_id": "python/b", "pass_at_k": 0.5, "samples_done": 2},
        {"task_id": "rust/c", "pass_at_k": 0.0, "samples_done": 0},
    ]
    assert "samples" not in run


def test_runs_without_include_have_no_task_scores(client):
    _add_runs("a")
    (run,) = client.get("/api/runs").json()
    assert "task_scores" not in run


def test_runs_reject_unknown_include(client):
    assert client.get("/api/runs?include=samples").status_code == 400


def test_task_history_lists_runs_newest_first_with_failure_breakdown(client):
    from polybench.db import get_session
    from polybench.models import Sample, TaskResult

    older, newer = _add_runs("old-model", "new-model")
    with get_session() as session:
        for run_id, outcomes in [(older, [True, False]), (newer, [False, False])]:
            tr = TaskResult(
                run_id=run_id,
                task_id="python/two_sum",
                language="python",
                difficulty="easy",
                samples_generated=len(outcomes),
                samples_passed=sum(outcomes),
                task_pass_at_k=sum(outcomes) / len(outcomes),
            )
            session.add(tr)
            session.commit()
            for i, passed in enumerate(outcomes):
                kind = (
                    None
                    if passed
                    else ("compile_error" if run_id == newer else "wrong_output")
                )
                session.add(
                    Sample(
                        task_result_id=tr.id,
                        sample_index=i,
                        raw_output="",
                        passed=passed,
                        failure_kind=kind,
                    )
                )
        session.commit()

    history = client.get("/api/tasks/python/two_sum/results").json()

    assert history["task_id"] == "python/two_sum"
    assert [r["model"] for r in history["runs"]] == ["new-model", "old-model"]
    assert history["runs"][1]["samples_passed"] == 1
    assert history["failures"] == {"compile_error": 2, "wrong_output": 1}


def test_task_history_for_a_task_no_run_included_is_empty(client):
    history = client.get("/api/tasks/go/stack/results").json()
    assert history == {"task_id": "go/stack", "runs": [], "failures": {}}


def test_task_history_for_an_unknown_task_is_404(client):
    assert client.get("/api/tasks/python/nope/results").status_code == 404


def test_single_task_route_still_works_next_to_history(client):
    assert client.get("/api/tasks/go/stack").json()["id"] == "go/stack"
