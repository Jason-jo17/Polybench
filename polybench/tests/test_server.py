"""Tests for the PolyBench MCP server (server.py)."""

from __future__ import annotations

import io
import json

import pytest

from polybench.server import (
    _err,
    _handle,
    _ok,
    _read_message,
    _write_message,
    _tool_list_tasks,
    _tool_validate_tasks,
    _tool_get_run,
    _tool_get_task_results,
    _tool_compare_runs,
)


# ---------------------------------------------------------------------------
# Framing helpers
# ---------------------------------------------------------------------------


def _frame(obj: dict) -> bytes:
    body = json.dumps(obj).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8") + body


def test_read_message_basic():
    obj = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
    stream = io.BytesIO(_frame(obj))
    result = _read_message(stream)
    assert result == obj


def test_read_message_eof():
    stream = io.BytesIO(b"")
    assert _read_message(stream) is None


def test_write_message_roundtrip():
    obj = {"jsonrpc": "2.0", "id": 2, "result": {"ok": True}}
    buf = io.BytesIO()
    _write_message(buf, obj)
    buf.seek(0)
    result = _read_message(buf)
    assert result == obj


def test_ok_helper():
    r = _ok(5, {"hello": "world"})
    assert r["id"] == 5
    assert r["result"] == {"hello": "world"}


def test_err_helper():
    r = _err(3, -32601, "not found")
    assert r["error"]["code"] == -32601
    assert "not found" in r["error"]["message"]


# ---------------------------------------------------------------------------
# _handle router
# ---------------------------------------------------------------------------


def test_handle_initialize():
    req = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    resp = _handle(req)
    assert resp is not None
    assert resp["result"]["serverInfo"]["name"] == "polybench-mcp"


def test_handle_initialized_notification():
    req = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    resp = _handle(req)
    assert resp is None


def test_handle_tools_list():
    req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    resp = _handle(req)
    assert resp is not None
    tool_names = [t["name"] for t in resp["result"]["tools"]]
    assert "list_tasks" in tool_names
    assert "validate_tasks" in tool_names
    assert "get_run" in tool_names
    assert "compare_runs" in tool_names
    assert "get_task_results" in tool_names


def test_handle_unknown_method():
    req = {"jsonrpc": "2.0", "id": 3, "method": "nonexistent"}
    resp = _handle(req)
    assert resp is not None
    assert "error" in resp
    assert resp["error"]["code"] == -32601


def test_handle_unknown_tool():
    req = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "does_not_exist", "arguments": {}},
    }
    resp = _handle(req)
    assert resp is not None
    assert "error" in resp


# ---------------------------------------------------------------------------
# Tool function unit tests
# ---------------------------------------------------------------------------


def test_tool_list_tasks(tmp_path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "t.json").write_text(
        json.dumps(
            {
                "id": "python/test",
                "language": "python",
                "difficulty": "easy",
                "title": "T",
                "prompt": "P",
                "signature": "S",
                "test_code": "pass",
            }
        )
    )
    result = _tool_list_tasks({"tasks_dir": str(tasks_dir)})
    data = json.loads(result)
    assert len(data) == 1
    assert data[0]["id"] == "python/test"


def test_tool_list_tasks_with_filter(tmp_path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "t.json").write_text(
        json.dumps(
            {
                "id": "go/foo",
                "language": "go",
                "difficulty": "hard",
                "title": "T",
                "prompt": "P",
                "signature": "S",
                "test_code": "pass",
            }
        )
    )
    result = _tool_list_tasks({"tasks_dir": str(tasks_dir), "lang": "python"})
    data = json.loads(result)
    assert data == []


def test_tool_validate_tasks_ok(tmp_path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "t.json").write_text(
        json.dumps(
            {
                "id": "python/test",
                "language": "python",
                "difficulty": "easy",
                "title": "T",
                "prompt": "P",
                "signature": "S",
                "test_code": "pass",
            }
        )
    )
    result = _tool_validate_tasks({"tasks_dir": str(tasks_dir)})
    assert "OK" in result


def test_tool_validate_tasks_bad_json(tmp_path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "t.json").write_text("not json at all")
    result = _tool_validate_tasks({"tasks_dir": str(tasks_dir)})
    assert "VALIDATION FAILED" in result


def test_tool_get_run_not_found(tmp_db):
    result = _tool_get_run({"run_id": "nonexistent", "db": str(tmp_db)})
    assert "No run found" in result


def test_tool_get_run_found(tmp_db):
    from polybench.db import get_session
    from polybench.models import BenchmarkRun

    run = BenchmarkRun(
        model="claude-sonnet-4-6",
        provider="mock",
        samples_per_task=1,
        k=1,
        temperature=0.2,
        total_tasks=1,
        pass_at_k=1.0,
    )
    with get_session() as session:
        session.add(run)
        session.commit()
        run_id = run.id

    result = _tool_get_run({"run_id": run_id, "db": str(tmp_db)})
    data = json.loads(result)
    assert data["id"] == run_id
    assert data["model"] == "claude-sonnet-4-6"


def test_tool_get_task_results_empty(tmp_db):
    result = _tool_get_task_results({"run_id": "norun", "db": str(tmp_db)})
    assert "No task results" in result


def test_tool_get_task_results_found(tmp_db):
    from polybench.db import get_session
    from polybench.models import BenchmarkRun, TaskResult

    run = BenchmarkRun(
        model="m",
        provider="mock",
        samples_per_task=1,
        k=1,
        temperature=0.0,
        total_tasks=1,
        pass_at_k=0.0,
    )
    with get_session() as session:
        session.add(run)
        session.commit()
        tr = TaskResult(
            run_id=run.id,
            task_id="python/t",
            language="python",
            difficulty="easy",
            samples_generated=1,
            samples_passed=1,
            task_pass_at_k=1.0,
            sandbox_image="polybench-python:local",
            sandbox_test_cmd="python -m pytest -q test_solution.py",
        )
        session.add(tr)
        session.commit()
        run_id = run.id

    result = _tool_get_task_results({"run_id": run_id, "db": str(tmp_db)})
    data = json.loads(result)
    assert len(data) == 1
    assert data[0]["task_id"] == "python/t"
    assert data[0]["sandbox_image"] == "polybench-python:local"


def test_tool_compare_runs(tmp_db):
    from polybench.db import get_session
    from polybench.models import BenchmarkRun, TaskResult

    def _make_run(model: str) -> str:
        run = BenchmarkRun(
            model=model,
            provider="mock",
            samples_per_task=1,
            k=1,
            temperature=0.0,
            total_tasks=1,
            pass_at_k=0.0,
        )
        with get_session() as session:
            session.add(run)
            session.commit()
            rid = run.id
        return rid

    rid_a = _make_run("m-a")
    rid_b = _make_run("m-b")

    with get_session() as session:
        session.add(
            TaskResult(
                run_id=rid_a,
                task_id="python/t",
                language="python",
                difficulty="easy",
                samples_generated=2,
                samples_passed=2,
                task_pass_at_k=1.0,
            )
        )
        session.add(
            TaskResult(
                run_id=rid_b,
                task_id="python/t",
                language="python",
                difficulty="easy",
                samples_generated=2,
                samples_passed=1,
                task_pass_at_k=0.5,
            )
        )
        session.commit()

    result = _tool_compare_runs({"run_a": rid_a, "run_b": rid_b, "db": str(tmp_db)})
    data = json.loads(result)
    assert len(data) == 1
    assert data[0]["delta"] == pytest.approx(-0.5)


def test_handle_tools_call_list_tasks(tmp_path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "t.json").write_text(
        json.dumps(
            {
                "id": "python/test",
                "language": "python",
                "difficulty": "easy",
                "title": "T",
                "prompt": "P",
                "signature": "S",
                "test_code": "pass",
            }
        )
    )
    req = {
        "jsonrpc": "2.0",
        "id": 10,
        "method": "tools/call",
        "params": {"name": "list_tasks", "arguments": {"tasks_dir": str(tasks_dir)}},
    }
    resp = _handle(req)
    assert resp is not None
    assert "result" in resp
    content = resp["result"]["content"][0]["text"]
    assert "python/test" in content


def test_handle_tools_call_error_propagates(tmp_path):
    req = {
        "jsonrpc": "2.0",
        "id": 11,
        "method": "tools/call",
        "params": {"name": "get_run", "arguments": {}},  # missing required run_id
    }
    resp = _handle(req)
    assert resp is not None
    assert "error" in resp
