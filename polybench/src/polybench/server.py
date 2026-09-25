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
  run_benchmark     — start a benchmark run in the background
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

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
    return json.loads(body.decode("utf-8"))  # type: ignore[no-any-return]


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

_TASKS_DEFAULT = str(Path(__file__).resolve().parents[3] / "tasks")
_DB_DEFAULT = str(Path(__file__).resolve().parents[3] / "polybench.db")


def _require_args(args: dict[str, Any], *keys: str) -> None:
    missing = [k for k in keys if args.get(k) is None]
    if missing:
        raise ValueError(f"Missing required argument(s): {', '.join(missing)}")


def _tool_list_tasks(args: dict[str, Any]) -> str:
    from polybench.tasks.loader import load_tasks
    from polybench.tasks.registry import TaskRegistry

    tasks_dir = args.get("tasks_dir", _TASKS_DEFAULT)
    lang = args.get("lang")
    difficulty = args.get("difficulty")

    loaded = list(load_tasks(tasks_dir))
    registry = TaskRegistry(loaded)
    filtered = registry.filter(lang=lang, difficulty=difficulty)

    rows = [
        {
            "id": t.id,
            "language": t.language,
            "difficulty": t.difficulty.value,
            "tags": t.tags,
        }
        for t in filtered
    ]
    return json.dumps(rows, indent=2)


def _tool_validate_tasks(args: dict[str, Any]) -> str:
    from polybench.tasks.loader import load_tasks

    tasks_dir = args.get("tasks_dir", _TASKS_DEFAULT)
    errors: list[str] = []
    count = 0
    try:
        for task in load_tasks(tasks_dir):
            count += 1
            _ = task
    except Exception as exc:
        errors.append(str(exc))

    if errors:
        return "VALIDATION FAILED:\n" + "\n".join(errors)
    return f"OK — {count} tasks validated successfully."


def _tool_get_run(args: dict[str, Any]) -> str:
    from polybench.db import init_db, get_session
    from polybench.models import BenchmarkRun

    _require_args(args, "run_id")
    run_id: str = args["run_id"]
    db = args.get("db", _DB_DEFAULT)
    init_db(db)
    with get_session() as session:
        run = session.get(BenchmarkRun, run_id)
        if run is None:
            return f"No run found with id={run_id}"
        return json.dumps(
            {
                "id": run.id,
                "model": run.model,
                "provider": run.provider,
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
    from polybench.db import init_db, get_session
    from polybench.models import TaskResult
    from sqlmodel import select

    _require_args(args, "run_id")
    run_id: str = args["run_id"]
    db = args.get("db", _DB_DEFAULT)
    init_db(db)
    with get_session() as session:
        results = session.exec(
            select(TaskResult).where(TaskResult.run_id == run_id)
        ).all()
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
    from polybench.db import init_db, get_session
    from polybench.models import TaskResult
    from sqlmodel import select

    _require_args(args, "run_a", "run_b")
    run_a: str = args["run_a"]
    run_b: str = args["run_b"]
    db = args.get("db", _DB_DEFAULT)
    init_db(db)
    with get_session() as session:
        a_rows = session.exec(
            select(TaskResult).where(TaskResult.run_id == run_a)
        ).all()
        b_rows = session.exec(
            select(TaskResult).where(TaskResult.run_id == run_b)
        ).all()

    a_map = {r.task_id: r.task_pass_at_k for r in a_rows}
    b_map = {r.task_id: r.task_pass_at_k for r in b_rows}

    rows = []
    for task_id in sorted(set(a_map) | set(b_map)):
        va = a_map.get(task_id, 0.0)
        vb = b_map.get(task_id, 0.0)
        rows.append(
            {"task_id": task_id, "run_a": va, "run_b": vb, "delta": round(vb - va, 4)}
        )

    return json.dumps(rows, indent=2)


def _tool_run_benchmark(args: dict[str, Any]) -> str:
    import threading
    import subprocess
    from polybench.db import init_db, get_session
    from polybench.models import BenchmarkRun
    from polybench.engine import RunConfig
    from polybench.providers.anthropic_provider import AnthropicProvider
    from polybench.providers.mock_provider import MockProvider
    from polybench.providers.openai_compatible import OpenAICompatibleProvider
    from polybench.config import settings as _s
    from polybench.api.worker import execute_benchmark_run
    from polybench.tasks.loader import load_tasks
    from polybench.tasks.registry import TaskRegistry

    _require_args(args, "model", "provider")
    db = args.get("db", _DB_DEFAULT)
    tasks_dir = args.get("tasks_dir", _TASKS_DEFAULT)
    provider_name: str = args["provider"]
    model_name: str = args["model"]
    temperature: float = float(args.get("temperature", 0.2))

    _COMPAT_URLS: dict[str, str] = {
        "openai": "https://api.openai.com/v1",
        "groq": "https://api.groq.com/openai/v1",
        "together": "https://api.together.xyz/v1",
        "mistral": "https://api.mistral.ai/v1",
        "deepseek": "https://api.deepseek.com/v1",
    }
    try:
        if provider_name == "anthropic":
            provider_impl = AnthropicProvider(model=model_name, temperature=temperature)
        elif provider_name == "mock":
            provider_impl = MockProvider(model=model_name, temperature=temperature)
        elif provider_name in _COMPAT_URLS:
            api_key = getattr(_s, f"{provider_name}_api_key", None)
            if not api_key:
                return f"Error: Missing API key for provider '{provider_name}'."
            provider_impl = OpenAICompatibleProvider(
                api_key=api_key,
                base_url=_COMPAT_URLS[provider_name],
                model=model_name,
                temperature=temperature,
            )
        else:
            return f"Error: Unknown provider '{provider_name}'."
    except Exception as exc:
        return f"Error creating provider: {exc}"

    cfg = RunConfig(
        model=model_name,
        provider=provider_name,
        n=int(args.get("n", 5)),
        k=int(args.get("k", 1)),
        temperature=temperature,
        lang=args.get("lang"),
        tags=args.get("tags"),
    )

    git_sha: str | None = None
    try:
        git_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        pass

    loaded = list(load_tasks(tasks_dir))
    registry = TaskRegistry(loaded)
    filtered = registry.filter(lang=cfg.lang, tags=cfg.tags)

    if not filtered:
        return "Error: No tasks match the given filters."

    init_db(db)
    with get_session() as session:
        run_record = BenchmarkRun(
            model=cfg.model,
            provider=cfg.provider,
            language_filter=cfg.lang,
            samples_per_task=cfg.n,
            k=cfg.k,
            temperature=cfg.temperature,
            total_tasks=len(filtered),
            pass_at_k=0.0,
            status="PENDING",
            git_sha=git_sha,
        )
        session.add(run_record)
        session.commit()
        run_id = run_record.id

    t = threading.Thread(
        target=execute_benchmark_run, args=(run_id, cfg, provider_impl, Path(tasks_dir))
    )
    t.daemon = True
    t.start()

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
                    "description": "Provider name (e.g. openai, anthropic, mock)",
                },
                "n": {"type": "integer", "description": "Samples per task (default 5)"},
                "k": {"type": "integer", "description": "Pass@k parameter (default 1)"},
                "temperature": {
                    "type": "number",
                    "description": "Sampling temperature (default 0.2)",
                },
                "lang": {"type": "string", "description": "Language filter (optional)"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags filter (optional)",
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
