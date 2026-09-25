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
