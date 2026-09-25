"""
PolyBench MCP Server — stdio JSON-RPC 2.0 (Model Context Protocol).

Implements the MCP wire protocol directly so no external mcp SDK is required.
Clients connect via stdin/stdout; each message is a Content-Length framed
JSON-RPC 2.0 object (same framing as LSP).

Tools exposed:
  list_tasks        — list benchmark tasks with optional lang/difficulty filter
  validate_tasks    — validate all task files, report errors
  get_run           — fetch a BenchmarkRun record by run_id
  compare_runs      — side-by-side pass@k for two run IDs
  get_task_results  — fetch TaskResult rows for a given run_id
  list_providers    — which LLM providers are available and configured
  run_benchmark     — start a benchmark run in the background

The tools are thin wrappers over polybench.core, the layer the CLI and the
HTTP API share, so a run started here behaves exactly like one started there.
"""

from __future__ import annotations

import json
import sys
import threading
import traceback
from typing import Any

from polybench.compare import compare_runs
from polybench.config import PROJECT_ROOT
from polybench.core import runs as core_runs
from polybench.core.providers import (
    ALL_PROVIDERS,
    CLOUD_PROVIDERS,
    ProviderError,
    is_configured,
)
from polybench.core.tasks import parse_tags, public_task, select_tasks
from polybench.db import get_session, init_db
from polybench.models import BenchmarkRun
from polybench.tasks.loader import load_tasks

# ---------------------------------------------------------------------------
# Low-level MCP / LSP framing helpers
# ---------------------------------------------------------------------------


def _read_message(stream: Any) -> dict[str, Any] | None:
    """Read one Content-Length framed JSON message from a binary stream."""
    headers: dict[str, str] = {}
    while True:
        raw = stream.readline()
        if not raw:
            return None
        line = raw.decode("utf-8").rstrip("\r\n")
        if not line:
            break
        if ":" in line:
            k, _, v = line.partition(":")
            headers[k.strip().lower()] = v.strip()

    length = int(headers.get("content-length", "0"))
    if length == 0:
        return None
    body = stream.read(length)
    message: dict[str, Any] = json.loads(body.decode("utf-8"))
    return message


def _write_message(stream: Any, obj: dict[str, Any]) -> None:
    body = json.dumps(obj).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
    stream.write(header + body)
    stream.flush()


def _ok(req_id: int | str | None, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id: int | str | None, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

_TASKS_DEFAULT = str(PROJECT_ROOT / "tasks")
_DB_DEFAULT = str(PROJECT_ROOT / "polybench.db")


def _require_args(args: dict[str, Any], *keys: str) -> None:
    missing = [k for k in keys if args.get(k) is None]
    if missing:
        raise ValueError(f"Missing required argument(s): {', '.join(missing)}")


def _tool_list_tasks(args: dict[str, Any]) -> str:
    tasks = select_tasks(
        args.get("tasks_dir", _TASKS_DEFAULT),
        lang=args.get("lang"),
        difficulty=args.get("difficulty"),
        tags=parse_tags(args.get("tags")),
    )
    return json.dumps([public_task(t, detail=False) for t in tasks], indent=2)


def _tool_validate_tasks(args: dict[str, Any]) -> str:
    try:
        count = sum(1 for _ in load_tasks(args.get("tasks_dir", _TASKS_DEFAULT)))
    except Exception as exc:
        return f"VALIDATION FAILED:\n{exc}"
    return f"OK — {count} tasks validated successfully."


def _tool_get_run(args: dict[str, Any]) -> str:
    _require_args(args, "run_id")
    run_id: str = args["run_id"]
    init_db(args.get("db", _DB_DEFAULT))
    with get_session() as session:
        run = session.get(BenchmarkRun, run_id)
        if run is None:
            return f"No run found with id={run_id}"
        return json.dumps(
            {
                "id": run.id,
                "model": run.model,
                "provider": run.provider,
                "status": run.status,
                "created_at": str(run.created_at),
                "total_tasks": run.total_tasks,
                "samples_per_task": run.samples_per_task,
                "k": run.k,
                "pass_at_k": run.pass_at_k,
                "temperature": run.temperature,
                "language_filter": run.language_filter,
                "git_sha": run.git_sha,
            },
            indent=2,
        )


def _tool_get_task_results(args: dict[str, Any]) -> str:
    _require_args(args, "run_id")
    run_id: str = args["run_id"]
    init_db(args.get("db", _DB_DEFAULT))
    with get_session() as session:
        results = core_runs.task_results(session, run_id)
        if not results:
            return f"No task results for run_id={run_id}"
        rows = [
            {
                "task_id": r.task_id,
                "language": r.language,
                "difficulty": r.difficulty,
                "samples_generated": r.samples_generated,
                "samples_passed": r.samples_passed,
                "task_pass_at_k": r.task_pass_at_k,
                "sandbox_image": r.sandbox_image,
                "sandbox_test_cmd": r.sandbox_test_cmd,
            }
            for r in results
        ]
        return json.dumps(rows, indent=2)


def _tool_compare_runs(args: dict[str, Any]) -> str:
    _require_args(args, "run_a", "run_b")
    init_db(args.get("db", _DB_DEFAULT))
    with get_session() as session:
        rows = compare_runs(session, args["run_a"], args["run_b"])
    return json.dumps([row.to_dict() for row in rows], indent=2)


def _tool_list_providers(args: dict[str, Any]) -> str:
    rows = [
        {
            "provider": p,
            "configured": is_configured(p),
            "requires_key": p in CLOUD_PROVIDERS,
        }
        for p in ALL_PROVIDERS
    ]
    return json.dumps(rows, indent=2)


def _tool_run_benchmark(args: dict[str, Any]) -> str:
    _require_args(args, "model", "provider")
    try:
        plan = core_runs.plan_run(
            provider=args["provider"],
            model=args["model"],
            tasks_dir=args.get("tasks_dir", _TASKS_DEFAULT),
            samples=int(args.get("n", 5)),
            k=int(args.get("k", 1)),
            temperature=float(args.get("temperature", 0.2)),
            lang=args.get("lang"),
            difficulty=args.get("difficulty"),
            tags=parse_tags(args.get("tags")),
        )
    except (ProviderError, core_runs.NoTasksError) as exc:
        return f"Error: {exc}"
    except Exception as exc:  # e.g. the provider's client failing to initialise
        return f"Error preparing the run: {exc}"

    init_db(args.get("db", _DB_DEFAULT))
    with get_session() as session:
        run_id = core_runs.start_run(session, plan).id

    threading.Thread(
        target=core_runs.execute_run, args=(run_id, plan), daemon=True
    ).start()
    return f"Benchmark run {run_id} started in background. Use get_run or get_task_results to monitor."


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

_TOOLS = [
    {
        "name": "list_tasks",
        "description": "List PolyBench benchmark tasks. Optionally filter by language or difficulty.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tasks_dir": {
                    "type": "string",
                    "description": "Path to tasks directory",
                },
                "lang": {
                    "type": "string",
                    "description": "Language filter (python/javascript/go/rust)",
                },
                "difficulty": {
                    "type": "string",
                    "description": "Difficulty filter (easy/medium/hard)",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Only tasks with all of these tags",
                },
            },
            "required": [],
        },
    },
    {
        "name": "validate_tasks",
        "description": "Validate all task JSON files against the Task schema.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tasks_dir": {
                    "type": "string",
                    "description": "Path to tasks directory",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_run",
        "description": "Fetch a BenchmarkRun record by run_id from the SQLite database.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "The run ID to fetch"},
                "db": {"type": "string", "description": "Path to polybench.db"},
            },
            "required": ["run_id"],
        },
    },
    {
        "name": "get_task_results",
        "description": "Fetch all TaskResult rows for a given run_id, including sandbox config.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "The run ID"},
                "db": {"type": "string", "description": "Path to polybench.db"},
            },
            "required": ["run_id"],
        },
    },
    {
        "name": "compare_runs",
        "description": "Compare pass@k scores for two run IDs side-by-side.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_a": {"type": "string", "description": "First run ID"},
                "run_b": {"type": "string", "description": "Second run ID"},
                "db": {"type": "string", "description": "Path to polybench.db"},
            },
            "required": ["run_a", "run_b"],
        },
    },
    {
        "name": "list_providers",
        "description": "List the LLM providers PolyBench supports and whether each is configured.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "run_benchmark",
        "description": "Start a new benchmark run in the background.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model": {
                    "type": "string",
                    "description": "Model name (e.g. gpt-4o, claude-3-5-sonnet)",
                },
                "provider": {
                    "type": "string",
                    "description": "Provider name (see list_providers), e.g. anthropic, openai, ollama or mock",
                },
                "n": {"type": "integer", "description": "Samples per task (default 5)"},
                "k": {"type": "integer", "description": "Pass@k parameter (default 1)"},
                "temperature": {
                    "type": "number",
                    "description": "Sampling temperature (default 0.2)",
                },
                "lang": {"type": "string", "description": "Language filter (optional)"},
                "difficulty": {
                    "type": "string",
                    "description": "Difficulty filter: easy/medium/hard (optional)",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Only tasks with all of these tags (optional)",
                },
                "db": {"type": "string", "description": "Path to polybench.db"},
                "tasks_dir": {
                    "type": "string",
                    "description": "Path to tasks directory",
                },
            },
            "required": ["model", "provider"],
        },
    },
]

_TOOL_FNS = {
    "list_tasks": _tool_list_tasks,
    "validate_tasks": _tool_validate_tasks,
    "get_run": _tool_get_run,
    "get_task_results": _tool_get_task_results,
    "compare_runs": _tool_compare_runs,
    "list_providers": _tool_list_providers,
    "run_benchmark": _tool_run_benchmark,
}


# ---------------------------------------------------------------------------
# Request router
# ---------------------------------------------------------------------------


def _handle(req: dict[str, Any]) -> dict[str, Any] | None:
    method = req.get("method", "")
    req_id = req.get("id")

    if method == "initialize":
        return _ok(
            req_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "polybench-mcp", "version": "0.1.0"},
            },
        )

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return _ok(req_id, {"tools": _TOOLS})

    if method == "tools/call":
        params = req.get("params", {})
        name: str = params.get("name", "")
        tool_args: dict[str, Any] = params.get("arguments", {})
        fn = _TOOL_FNS.get(name)
        if fn is None:
            return _err(req_id, -32601, f"Unknown tool: {name}")
        try:
            text = fn(tool_args)
            return _ok(req_id, {"content": [{"type": "text", "text": text}]})
        except Exception:
            tb = traceback.format_exc()
            return _err(req_id, -32603, tb)

    return _err(req_id, -32601, f"Method not found: {method}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    # stdout carries the protocol, so anything else written there (the engine's
    # progress bar, a stray print) would corrupt it. Send all of that to stderr.
    sys.stdout = sys.stderr
    while True:
        try:
            msg = _read_message(stdin)
        except Exception:
            break
        if msg is None:
            break
        response = _handle(msg)
        if response is not None:
            _write_message(stdout, response)


if __name__ == "__main__":
    main()
