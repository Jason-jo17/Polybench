# PolyBench — Claude Code Build Prompt

> Copy everything below this line into Claude Code (or paste as a `CLAUDE.md` at the repo root). It is a complete engineering spec — build it exactly as written.

---

## Context

**PolyBench** is a polyglot AI coding-benchmark harness. It sends real-world programming tasks to frontier LLMs (Claude, GPT), extracts the generated code, executes it inside a hardened sandbox against a hidden test suite, and scores model performance using `pass@k` plus a structured failure taxonomy. It supports Python, JavaScript, and Go tasks and emits both terminal and HTML evaluation reports.

- **Who it's for:** A demonstration of AI-evaluation engineering — designing coding benchmarks, analyzing AI-generated code for correctness and edge-case failures, and running them at scale with full CI/CD and test coverage.
- **What already exists:** Nothing. Greenfield build.
- **Design goals (non-negotiable):** clean typed Python, ≥90% test coverage on the harness itself, deterministic + reproducible runs, isolated/secure code execution, zero `# type: ignore` outside vendored stubs.

---

## Technical Stack (exact versions)

- **Language:** Python 3.12 (target), CI matrix on 3.11 + 3.12
- **Packaging:** `pyproject.toml` (PEP 621), managed with `uv` (fall back to `pip` if `uv` unavailable)
- **CLI:** Typer 0.12.x + Rich 13.7.x (tables, progress bars)
- **Data validation:** Pydantic 2.7.x
- **Persistence:** SQLite via SQLModel 0.0.21 (no external DB) + JSONL run artifacts
- **LLM clients:** `anthropic` 0.34.x (primary), `openai` 1.40.x (optional second provider)
- **Templating (HTML report):** Jinja2 3.1.x
- **Sandbox runtime:** Docker (subprocess-driven `docker run`); graceful "sandbox unavailable" error if the daemon is absent
- **Lint/format:** Ruff 0.6.x (lint + format), Mypy 1.11.x in `strict` mode
- **Testing:** Pytest 8.3.x, pytest-cov 5.0.x, Hypothesis 6.108.x (property-based), pytest-mock 3.14.x
- **Pre-commit:** pre-commit 3.8.x
- **CI:** GitHub Actions

Always pin versions in `pyproject.toml`. Never use `latest`.

---

## Directory Structure

Build this exact tree. Each file's purpose is in the comment.

```
polybench/
├── pyproject.toml                  # PEP 621 metadata, deps, tool configs (ruff/mypy/pytest)
├── README.md                       # quickstart, architecture diagram, sample report screenshot
├── .pre-commit-config.yaml         # ruff + mypy + end-of-file fixer hooks
├── .env.example                    # template for required env vars
├── .gitignore
├── .dockerignore
├── sandbox/
│   ├── Dockerfile.python           # python:3.12-slim, non-root user, no extra packages
│   ├── Dockerfile.node             # node:20-slim, non-root user
│   └── Dockerfile.go               # golang:1.22-alpine, non-root user
├── src/
│   └── polybench/
│       ├── __init__.py             # exports __version__
│       ├── cli.py                  # Typer app; wires up all commands
│       ├── config.py               # Settings (Pydantic BaseSettings) — env-driven
│       ├── models.py               # SQLModel tables: BenchmarkRun, TaskResult, Sample
│       ├── schemas.py              # Pydantic schemas: Task, TestCase, GenerationResult, ScoreReport
│       ├── db.py                   # engine factory, session context manager, create_all
│       ├── tasks/
│       │   ├── __init__.py
│       │   ├── loader.py           # load + validate task files from /tasks dir
│       │   └── registry.py         # in-memory registry, filtering by lang/difficulty/tag
│       ├── providers/
│       │   ├── __init__.py
│       │   ├── base.py             # LLMProvider Protocol: generate(prompt) -> GenerationResult
│       │   ├── anthropic_provider.py
│       │   ├── openai_provider.py
│       │   └── mock_provider.py    # deterministic provider for tests (no network)
│       ├── extract.py              # parse code block out of model output; lang-aware
│       ├── sandbox/
│       │   ├── __init__.py
│       │   ├── runner.py           # SandboxRunner: build cmd, docker run, capture, kill on timeout
│       │   ├── policy.py           # SandboxPolicy: cpu/mem/pids/timeout/network constants
│       │   └── languages.py        # per-language exec spec (image, test cmd, file layout)
│       ├── scoring/
│       │   ├── __init__.py
│       │   ├── passk.py            # unbiased pass@k estimator
│       │   └── taxonomy.py         # FailureKind enum + classifier(stdout, stderr, exit_code)
│       ├── engine.py               # orchestrates: load task -> generate n samples -> run -> score -> persist
│       └── report/
│           ├── __init__.py
│           ├── html.py             # render Jinja2 report from a run id
│           └── templates/
│               └── report.html.j2
├── tasks/                          # the benchmark dataset (the "problems")
│   ├── python/
│   │   ├── lru_cache.json
│   │   └── version_compare.json
│   ├── javascript/
│   │   └── debounce.json
│   └── go/
│       └── safe_counter.json
└── tests/
    ├── conftest.py                 # fixtures: tmp db, mock provider, sample task
    ├── test_loader.py
    ├── test_extract.py             # incl. Hypothesis property tests
    ├── test_passk.py               # incl. Hypothesis property tests
    ├── test_taxonomy.py
    ├── test_engine.py              # full pipeline with mock provider + fake sandbox
    ├── test_sandbox_policy.py
    └── test_cli.py                 # Typer CliRunner smoke tests
```

The directory tree is the build map. Do not deviate from it.

---

## Data Schema

### Persistence models (`src/polybench/models.py`, SQLModel)

```python
from datetime import datetime
from sqlmodel import SQLModel, Field
import uuid

def _id() -> str:
    return uuid.uuid4().hex

class BenchmarkRun(SQLModel, table=True):
    id: str = Field(default_factory=_id, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    model: str                       # e.g. "claude-sonnet-4-6"
    provider: str                    # "anthropic" | "openai" | "mock"
    language_filter: str | None = None
    samples_per_task: int            # n in pass@k
    k: int                           # k in pass@k
    temperature: float
    total_tasks: int
    pass_at_k: float                 # aggregate across tasks
    git_sha: str | None = None       # for reproducibility

class TaskResult(SQLModel, table=True):
    id: str = Field(default_factory=_id, primary_key=True)
    run_id: str = Field(foreign_key="benchmarkrun.id", index=True)
    task_id: str                     # the task slug, e.g. "python/lru_cache"
    language: str
    difficulty: str                  # "easy" | "medium" | "hard"
    samples_generated: int           # n
    samples_passed: int              # c
    task_pass_at_k: float

class Sample(SQLModel, table=True):
    id: str = Field(default_factory=_id, primary_key=True)
    task_result_id: str = Field(foreign_key="taskresult.id", index=True)
    sample_index: int
    raw_output: str                  # full model text
    extracted_code: str | None       # None if extraction failed
    passed: bool
    failure_kind: str | None         # FailureKind value, None if passed
    exit_code: int | None
    stdout: str
    stderr: str
    runtime_ms: int
    timed_out: bool
```

### Task file schema (`src/polybench/schemas.py`, Pydantic v2)

Every task file in `/tasks` must validate against this. Reject on load if invalid.

```python
from pydantic import BaseModel, Field, field_validator
from enum import StrEnum

class Language(StrEnum):
    python = "python"
    javascript = "javascript"
    go = "go"

class Difficulty(StrEnum):
    easy = "easy"
    medium = "medium"
    hard = "hard"

class Task(BaseModel):
    id: str                          # "python/lru_cache" — must match path
    language: Language
    difficulty: Difficulty
    title: str
    prompt: str                      # the problem statement shown to the model
    signature: str                   # required function/class signature
    test_code: str                   # HIDDEN test suite (never shown to model)
    tags: list[str] = Field(default_factory=list)
    timeout_seconds: int = Field(default=10, ge=1, le=60)

    @field_validator("test_code")
    @classmethod
    def non_empty_tests(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("test_code must not be empty")
        return v
```

---

## CLI Commands (full signatures)

The CLI is the public interface. Implement each with Typer. All commands print a Rich table/summary and exit `0` on success, non-zero on error.

### `polybench run`
Run a benchmark.
- **Options:** `--model TEXT` (required), `--provider [anthropic|openai|mock]` (default `anthropic`), `--tasks PATH` (default `./tasks`), `--lang [python|javascript|go]` (optional filter), `--difficulty [easy|medium|hard]` (optional filter), `--samples/-n INT` (default 5), `-k INT` (default 1), `--temperature FLOAT` (default 0.2), `--db PATH` (default `./polybench.db`)
- **Logic:** load+filter tasks → for each task generate `n` samples → extract code → run each in sandbox → classify pass/fail → compute per-task `pass@k` → persist `BenchmarkRun`/`TaskResult`/`Sample` → print summary + the new `run_id`.
- **Errors:** exit 2 if no tasks match filter; exit 3 if provider auth missing; exit 4 if Docker unavailable.

### `polybench tasks list`
- **Options:** `--tasks PATH`, `--lang`, `--difficulty`
- Prints a table of task id / language / difficulty / tags.

### `polybench tasks validate`
- **Options:** `--tasks PATH`
- Loads every task file, validates against the `Task` schema, reports the first error per bad file. Exit 1 if any invalid.

### `polybench report`
- **Options:** `--run-id TEXT` (required), `--db PATH`, `--out PATH` (default `./report.html`)
- Renders the HTML report for that run and writes it. Prints the output path.

### `polybench compare`
- **Options:** `--run-a TEXT`, `--run-b TEXT`, `--db PATH`
- Prints a side-by-side table: per-task `pass@k` for A vs B and the aggregate delta.

### `polybench sandbox-test`
- **Options:** none
- Self-test that the sandbox enforces isolation. Runs three probe scripts inside the sandbox and asserts each is blocked: (1) outbound network call, (2) write outside `/tmp`, (3) fork bomb. Prints pass/fail per probe. Exit 1 if any isolation guarantee fails.

---

## Module Specifications

### `extract.py` — code extraction
- **Function:** `extract_code(raw: str, language: Language) -> str | None`
- **Behavior:** Prefer fenced blocks matching the language (```python / ```js / ```go); fall back to the first generic fenced block; fall back to the whole string if it parses as plausible code (heuristic: contains the `def`/`function`/`func` keyword for the language). Return `None` if nothing extractable.
- **Edge cases to handle:** multiple code blocks (take the longest), prose-wrapped code, mislabeled fences, leading "Here's my solution:" preamble.

### `sandbox/policy.py` — `SandboxPolicy` constants
```python
NETWORK = "none"          # --network none
MEMORY = "256m"           # --memory
CPUS = "1.0"              # --cpus
PIDS_LIMIT = 64           # --pids-limit
READ_ONLY = True          # --read-only root fs
TMPFS = "/tmp:rw,size=64m,noexec"   # only writable mount
USER = "10001:10001"      # non-root --user
WALL_CLOCK_BUFFER_S = 5   # add to task timeout before SIGKILL
CAP_DROP = "ALL"          # --cap-drop ALL
```

### `sandbox/runner.py` — `SandboxRunner`
- **Method:** `run(code: str, task: Task) -> SandboxResult`
- **Behavior:** write `code` + `task.test_code` into a tmp dir per `languages.py` layout; invoke `docker run` with every flag from `SandboxPolicy`, `--rm`, no host mounts except the read-only code injection via stdin/`COPY`-free tmpfs; capture stdout/stderr/exit code; enforce `task.timeout_seconds` via `subprocess.run(timeout=...)`, and on `TimeoutExpired` issue `docker kill` and mark `timed_out=True`.
- **Returns:** `SandboxResult(exit_code, stdout, stderr, runtime_ms, timed_out)`.
- **Security note (document in code):** generated code is fully untrusted; it only ever runs inside the container, never via `exec`/`eval` on the host.

### `sandbox/languages.py` — per-language exec spec
| Language | Image tag | Code file | Test cmd inside container |
|---|---|---|---|
| python | `polybench-python:local` | `solution.py` + `test_solution.py` | `python -m pytest -q test_solution.py` |
| javascript | `polybench-node:local` | `solution.js` + `test_solution.mjs` | `node --test test_solution.mjs` |
| go | `polybench-go:local` | `solution.go` + `solution_test.go` | `go test ./...` |

### `scoring/passk.py` — unbiased `pass@k`
Implement the standard unbiased estimator (Codex/HumanEval). For a task with `n` total samples and `c` correct:

```
pass@k = 1 - C(n - c, k) / C(n, k)      when (n - c) >= k
pass@k = 1.0                            otherwise
```

- **Function:** `pass_at_k(n: int, c: int, k: int) -> float`
- Use `math.comb`. Guard: raise `ValueError` if `k > n` or any arg negative. Aggregate `pass@k` across tasks is the unweighted mean of per-task values.

### `scoring/taxonomy.py` — failure classification
```python
class FailureKind(StrEnum):
    EXTRACTION_FAILED = "extraction_failed"   # no code parsed from output
    COMPILE_ERROR = "compile_error"           # syntax / build error
    RUNTIME_ERROR = "runtime_error"           # uncaught exception
    WRONG_OUTPUT = "wrong_output"             # tests ran, assertions failed
    TIMEOUT = "timeout"
    MEMORY_EXCEEDED = "memory_exceeded"
    SECURITY_VIOLATION = "security_violation" # attempted blocked syscall/network
```
- **Function:** `classify(exit_code: int, stdout: str, stderr: str, timed_out: bool) -> FailureKind | None` — returns `None` when the run passed. Classify by inspecting stderr signatures per language (e.g. `SyntaxError`/`SyntaxError:` → COMPILE_ERROR, `AssertionError`/`FAIL` → WRONG_OUTPUT, OOM kill exit 137 → MEMORY_EXCEEDED).

### `engine.py` — orchestration
- **Function:** `run_benchmark(cfg: RunConfig, tasks: list[Task], provider: LLMProvider, runner: SandboxRunner, session: Session) -> BenchmarkRun`
- Deterministic ordering; tags the run with the current `git rev-parse HEAD` if available. Uses a Rich progress bar over `tasks × samples`. Persists everything in one transaction per task.

---

## AI Integration (exact prompts)

### Generation prompt (sent to the model under evaluation)
**System prompt:**
```
You are an expert software engineer. Solve the given programming task.
Return ONLY the implementation as a single fenced code block in the target
language. Do not include explanations, tests, usage examples, or prose.
Match the required signature exactly.
```

**User prompt template:**
```
Language: {language}
Required signature:
{signature}

Task:
{prompt}
```

- **No test leakage:** `task.test_code` is NEVER included in any prompt. The model is scored against tests it has not seen.
- **Validation of output:** server-side, `extract.py` must recover a code block; if not, the sample is recorded with `failure_kind = EXTRACTION_FAILED` and `passed = False`. No fallback to "trust the prose."

### `mock_provider.py`
Deterministic, network-free. Given a task id it returns a canned correct or incorrect solution from an in-module dict, keyed so tests can assert both pass and fail paths. Used by the entire test suite — **no test may hit a real LLM API.**

---

## Data Constants — sample benchmark tasks (real content, build these files)

### `tasks/python/lru_cache.json`
```json
{
  "id": "python/lru_cache",
  "language": "python",
  "difficulty": "medium",
  "title": "LRU Cache",
  "prompt": "Implement an LRUCache class with a fixed capacity. get(key) returns the value or -1 if absent and marks the key most-recently-used. put(key, value) inserts/updates and evicts the least-recently-used key when over capacity. All operations must be O(1).",
  "signature": "class LRUCache:\n    def __init__(self, capacity: int) -> None: ...\n    def get(self, key: int) -> int: ...\n    def put(self, key: int, value: int) -> None: ...",
  "tags": ["data-structures", "design"],
  "timeout_seconds": 10,
  "test_code": "from solution import LRUCache\n\ndef test_basic_eviction():\n    c = LRUCache(2)\n    c.put(1, 1); c.put(2, 2)\n    assert c.get(1) == 1\n    c.put(3, 3)            # evicts key 2\n    assert c.get(2) == -1\n    c.put(4, 4)            # evicts key 1\n    assert c.get(1) == -1\n    assert c.get(3) == 3\n    assert c.get(4) == 4\n\ndef test_update_refreshes_recency():\n    c = LRUCache(2)\n    c.put(1, 1); c.put(2, 2)\n    c.put(1, 10)           # refresh key 1\n    c.put(3, 3)            # should evict key 2, not key 1\n    assert c.get(2) == -1\n    assert c.get(1) == 10\n\ndef test_capacity_one_edge():\n    c = LRUCache(1)\n    c.put(1, 1); c.put(2, 2)\n    assert c.get(1) == -1\n    assert c.get(2) == 2\n"
}
```

### `tasks/python/version_compare.json`
```json
{
  "id": "python/version_compare",
  "language": "python",
  "difficulty": "easy",
  "title": "Semantic Version Comparison",
  "prompt": "Implement compare_versions(a, b) returning -1 if a < b, 0 if equal, 1 if a > b. Versions are dot-separated integers of arbitrary length; missing trailing components are treated as 0 (so '1.0' == '1.0.0').",
  "signature": "def compare_versions(a: str, b: str) -> int: ...",
  "tags": ["parsing", "edge-cases"],
  "timeout_seconds": 5,
  "test_code": "from solution import compare_versions\n\ndef test_equal_with_trailing_zeros():\n    assert compare_versions('1.0', '1.0.0') == 0\n\ndef test_numeric_not_lexical():\n    assert compare_versions('1.10', '1.9') == 1\n\ndef test_basic_ordering():\n    assert compare_versions('2.0.1', '2.0.1') == 0\n    assert compare_versions('0.9.9', '1.0.0') == -1\n    assert compare_versions('1.2.3', '1.2.0') == 1\n"
}
```

### `tasks/javascript/debounce.json`
```json
{
  "id": "javascript/debounce",
  "language": "javascript",
  "difficulty": "medium",
  "title": "Debounce",
  "prompt": "Implement debounce(fn, waitMs) returning a debounced function: fn runs only after waitMs has elapsed since the last call. Rapid successive calls reset the timer; only the final call's arguments are used.",
  "signature": "export function debounce(fn, waitMs) { /* ... */ }",
  "tags": ["timers", "closures"],
  "timeout_seconds": 10,
  "test_code": "import test from 'node:test';\nimport assert from 'node:assert';\nimport { debounce } from './solution.js';\n\ntest('calls once after burst', async () => {\n  let calls = 0; let lastArg = null;\n  const d = debounce((x) => { calls++; lastArg = x; }, 50);\n  d(1); d(2); d(3);\n  await new Promise(r => setTimeout(r, 120));\n  assert.strictEqual(calls, 1);\n  assert.strictEqual(lastArg, 3);\n});\n"
}
```

### `tasks/go/safe_counter.json`
```json
{
  "id": "go/safe_counter",
  "language": "go",
  "difficulty": "hard",
  "title": "Concurrency-Safe Counter",
  "prompt": "Implement a SafeCounter with Inc() and Value() int that is safe under concurrent use by many goroutines. Package name must be 'solution'.",
  "signature": "package solution\n\ntype SafeCounter struct { /* ... */ }\nfunc (c *SafeCounter) Inc()\nfunc (c *SafeCounter) Value() int",
  "tags": ["concurrency", "mutex"],
  "timeout_seconds": 15,
  "test_code": "package solution\n\nimport (\n\t\"sync\"\n\t\"testing\"\n)\n\nfunc TestConcurrentInc(t *testing.T) {\n\tc := &SafeCounter{}\n\tvar wg sync.WaitGroup\n\tfor i := 0; i < 1000; i++ {\n\t\twg.Add(1)\n\t\tgo func() { defer wg.Done(); c.Inc() }()\n\t}\n\twg.Wait()\n\tif c.Value() != 1000 {\n\t\tt.Fatalf(\"expected 1000, got %d\", c.Value())\n\t}\n}\n"
}
```

---

## Environment Variables (`.env.example`)
```
ANTHROPIC_API_KEY=
OPENAI_API_KEY=            # optional, only for --provider openai
POLYBENCH_DB=./polybench.db
POLYBENCH_DEFAULT_MODEL=claude-sonnet-4-6
```
`config.py` loads these via Pydantic `BaseSettings`; a missing provider key only errors when that provider is actually selected.

---

## Testing Requirements

- **Coverage gate:** `pytest --cov=polybench --cov-fail-under=90`. The harness logic (extract, passk, taxonomy, loader, engine) must be ≥90%.
- **No network in tests:** every test uses `mock_provider` and a fake/in-memory `SandboxRunner` (a test double that returns scripted `SandboxResult`s). The real Docker runner is exercised only by an opt-in `@pytest.mark.docker` suite skipped by default.
- **Property-based tests (Hypothesis):**
  - `test_passk.py`: for random valid `(n, c, k)`, assert `0.0 <= pass_at_k(n, c, k) <= 1.0`, monotonic non-decreasing in `c`, and `pass_at_k(n, n, k) == 1.0`.
  - `test_extract.py`: for code wrapped in arbitrary prose + fences, extraction recovers the code body.
- **CLI tests:** Typer `CliRunner` smoke tests for every command, asserting exit codes and key output substrings.

---

## CI/CD — `.github/workflows/ci.yml`

Build this workflow exactly:

```yaml
name: ci
on:
  push: { branches: [main] }
  pull_request: { branches: [main] }
jobs:
  quality:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - name: Set up Python ${{ matrix.python-version }}
        run: uv python install ${{ matrix.python-version }}
      - name: Install
        run: uv sync --all-extras --dev
      - name: Ruff (lint)
        run: uv run ruff check .
      - name: Ruff (format check)
        run: uv run ruff format --check .
      - name: Mypy (strict)
        run: uv run mypy src
      - name: Pytest + coverage gate
        run: uv run pytest --cov=polybench --cov-report=term-missing --cov-fail-under=90
```

Also add `.pre-commit-config.yaml` with ruff (lint + format) and mypy hooks, and document `pre-commit install` in the README.

---

## Execution Order

1. `uv sync --all-extras --dev` — install everything.
2. `uv run polybench tasks validate` — confirm all task files parse. Must exit 0.
3. `docker build -t polybench-python:local -f sandbox/Dockerfile.python sandbox/` (repeat for node, go).
4. `uv run polybench sandbox-test` — confirm isolation guarantees hold. Must exit 0.
5. `uv run pytest --cov=polybench --cov-fail-under=90` — green, ≥90% coverage.
6. `uv run mypy src` — zero errors.
7. `uv run polybench run --provider mock --model demo -n 5 -k 1` — full pipeline end-to-end on the mock provider (no API key needed). Confirm a `run_id` prints and rows land in the DB.
8. `uv run polybench report --run-id <id>` — HTML report renders.
9. (Optional, real eval) set `ANTHROPIC_API_KEY`, then `uv run polybench run --model claude-sonnet-4-6 -n 10 -k 1`.

---

## Quality Rules (enforce throughout)

- Mypy `strict`; no `Any` in public signatures; no `# type: ignore` except vendored stubs (with a reason comment).
- Every CLI command has explicit exit codes and Rich-formatted output.
- Generated/untrusted code is executed **only** inside the Docker sandbox — never `exec`, `eval`, or a host subprocess of the model's code.
- Tasks never leak their hidden tests into prompts.
- Real task content only (the four tasks above) — no `foo`/`bar` placeholders.
- README includes: one-paragraph purpose, an ASCII architecture diagram (provider → extract → sandbox → scoring → report), the `pass@k` formula, and the security model of the sandbox.
