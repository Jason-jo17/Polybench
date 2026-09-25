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
