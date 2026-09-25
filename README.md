# PolyBench

PolyBench measures how well large language models write working code. It sends programming tasks to a model, pulls the code out of the response, runs it in an isolated Docker sandbox against a test suite the model never sees, and scores the results with pass@k. Every failure is classified: the code couldn't be extracted, didn't compile, crashed, gave the wrong output, timed out, used too much memory, or tried something the sandbox blocks.

It ships with 21 tasks in Python, JavaScript, Go and Rust, and works with Anthropic, OpenAI and any OpenAI-compatible provider, including local models through Ollama and LM Studio.

You can drive it three ways:

- **Dashboard**: a Next.js web app for starting runs, inspecting every sample, and comparing models task by task.
- **CLI**: `polybench run`, `compare`, `report`, `export` and more, with terminal and HTML reports.
- **MCP server**: lets an AI agent such as Claude Desktop list tasks, start runs and read results.

## Dashboard

Each run is shown as a grid with one row per task and one square per sample. Green squares passed and red ones failed. Select any square to see the code the model wrote, what the sandbox printed, and why the sample failed.

![Run detail: pass/fail squares for every sample of every task](docs/screenshots/run.png)

| Overview | Compare runs |
| --- | --- |
| ![Overview with the new-run form and recent runs](docs/screenshots/overview.png) | ![Two runs compared task by task](docs/screenshots/compare.png) |

The dashboard follows your system's light or dark setting ([dark mode screenshot](docs/screenshots/run-dark.png)). Screenshots use synthetic demo data, not real model results.

## How it works

```
 task (prompt + signature)
        │
        ▼
 ┌──────────────┐   n samples   ┌──────────────┐   code   ┌─────────────────┐   pass/fail   ┌──────────┐
 │ LLM provider │ ────────────▶ │ extract code │ ───────▶ │ Docker sandbox  │ ────────────▶ │ scoring  │
 └──────────────┘               └──────────────┘          │ + hidden tests  │               │ pass@k + │
                                                          └─────────────────┘               │ taxonomy │
                                                                                            └──────────┘
```

For each task the model is sampled `n` times. pass@k is the probability that at least one of `k` samples passes, computed with the unbiased estimator from the HumanEval paper:

```
pass@k = 1 − C(n − c, k) / C(n, k)      (c = samples that passed; 1.0 when n − c < k)
```

A run's score is the mean pass@k across its tasks.

### Sandbox isolation

Generated code is untrusted, so it never runs on the host through `exec` or `eval`. Each sample runs in a throwaway container with:

- no network access (`--network none`)
- no access to the host filesystem
- memory, CPU and process limits (256 MB and 1 CPU by default, set in `src/polybench/sandbox/policy.py`)
- a non-root user with Linux capabilities dropped
- a wall-clock timeout per task

Run `polybench sandbox-test` to check these limits on your machine.

## Requirements

- Python 3.11 or later and [uv](https://docs.astral.sh/uv/)
- Docker, running, for the sandbox
- Node.js 20 or later, for the dashboard
- An API key for any hosted provider you want to test. The `mock` provider needs no key and is useful for trying things out.

## Quickstart

All commands run from the `polybench/` directory.

```bash
cd polybench
uv sync --all-extras --dev
cp .env.example .env          # add the API keys you plan to use
uv run polybench setup        # builds the sandbox images
```

### From the command line

```bash
# Try the whole pipeline without an API key (see "Mock provider" below)
uv run polybench run --provider mock --model demo -n 3

# 5 samples per task, scored as pass@1, Python tasks only
uv run polybench run --provider anthropic --model claude-sonnet-4-6 -n 5 -k 1 --lang python

uv run polybench history           # recent runs
uv run polybench resume RUN_ID     # finish a run that was interrupted (keeps finished samples)
uv run polybench compare --run-a RUN_A --run-b RUN_B
uv run polybench report --run-id RUN_ID --out report.html
```

Add `--dry-run` to any `run` to list the tasks it would include without calling a model. Run `uv run polybench --help` for the full list of commands, including `tasks list`, `tasks verify`, `keys`, `export` and `compass` (checks which providers are reachable).

### With the dashboard

Start the API, then the web app in a second terminal:

```bash
uv run uvicorn polybench.api.main:app --port 8080
```

```bash
cd web
npm install
npm run dev
```

Open http://localhost:3000. If `POLYBENCH_DASHBOARD_PASSWORD` is set in `.env`, the browser asks for it; any username works. To point the dashboard at an API somewhere other than `http://127.0.0.1:8080`, set `POLYBENCH_API_URL` before `npm run dev` or `npm run build`.

### With Docker Compose

```bash
cd polybench
cp .env.example .env      # optional: API keys, POLYBENCH_DASHBOARD_PASSWORD, POSTGRES_PASSWORD
docker compose up -d --build
```

This starts Postgres, the API and the dashboard. The dashboard is at http://localhost:3000, and the API is also exposed at http://localhost:8001. If those ports are taken, set `POLYBENCH_WEB_PORT` and `POLYBENCH_API_PORT` in `.env`. The first run builds the four sandbox images, which takes a few minutes.

The API starts sandbox containers through the host's Docker socket, which gives it root-equivalent access to the host. Only run the stack on a machine you trust it with, and set a strong `POSTGRES_PASSWORD` in `polybench/.env` anywhere other than your own computer (`POSTGRES_USER` and `POSTGRES_DB` can be changed the same way).

### From an AI agent (MCP)

Add PolyBench to your MCP client's configuration, for example `claude_desktop_config.json`. [`mcp_config.example.json`](polybench/mcp_config.example.json) has the same snippet:

```json
{
  "mcpServers": {
    "polybench": {
      "command": "uv",
      "args": ["run", "python", "-m", "polybench.server"],
      "cwd": "/absolute/path/to/Polybench/polybench"
    }
  }
}
```

The server exposes tools to list and validate tasks, list the available providers, start a benchmark run, fetch a run and its per-task results, and compare two runs. It supports the same providers and filters as the CLI.

## Providers

| Provider | `--provider` | Needs |
| --- | --- | --- |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` |
| OpenAI | `openai` | `OPENAI_API_KEY` |
| Groq, Together, Mistral, DeepSeek, xAI, Gemini, Fireworks, Perplexity | `groq`, `together`, `mistral`, `deepseek`, `xai`, `gemini`, `fireworks`, `perplexity` | the matching `*_API_KEY` |
| Ollama | `ollama` | a running Ollama server (`OLLAMA_BASE_URL`) |
| LM Studio | `lmstudio` | a running LM Studio server (`LMSTUDIO_BASE_URL`) |
| Mock | `mock` | nothing; see below |

### Mock provider

The mock provider answers from each task's reference solution, so it exercises the real pipeline (code extraction, sandbox, scoring) in every language, with no API key or network. The model name sets how often it's right:

| `--model` | Behaviour |
| --- | --- |
| `demo` | correct about 70% of the time |
| `demo-40` (any number) | correct about that percentage of the time |
| `perfect` | always correct |
| `broken` | always returns the bare signature, which fails |

Results are deterministic: the same run always passes and fails the same samples.

## Configuration

Settings come from environment variables or `polybench/.env`. See [`.env.example`](polybench/.env.example) for the full list.

| Variable | Default | Purpose |
| --- | --- | --- |
| `POLYBENCH_DB` | `./polybench.db` | SQLite database for runs and results |
| `POLYBENCH_DEFAULT_MODEL` | `claude-sonnet-4-6` | model used when `--model` is omitted |
| `POLYBENCH_DASHBOARD_PASSWORD` | unset | if set, protects the dashboard and API with basic auth |
| `POLYBENCH_MAX_CONCURRENT_RUNS` | `1` | runs the API will execute at once |
| `POLYBENCH_SANDBOX_WORKERS` | `4` | samples run in parallel within a run, one container each |
| `POLYBENCH_RESUME_RUNS` | `true` | when the API restarts, finish interrupted runs instead of marking them failed |

## Adding tasks

Each task is a JSON file in `polybench/tasks/<language>/` with an `id`, `title`, `prompt`, the `signature` the model must implement, hidden `test_code`, a `reference_solution`, `difficulty`, `tags` and `timeout_seconds`. The tests and the reference solution are never shown to the model. Copy an existing task as a template, then check it:

```bash
uv run polybench tasks validate   # the file is well-formed
uv run polybench tasks verify     # in the sandbox: the reference passes, the bare signature fails
```

`tasks verify` guards the benchmark itself. Every task must be solvable, and its tests must reject an empty implementation.

See [CONTRIBUTING.md](CONTRIBUTING.md) for details, and [#15](https://github.com/Jason-jo17/Polybench/issues/15) for task ideas.

## Repository layout

```
polybench/
├── src/polybench/     # engine, providers, sandbox runner, scoring, CLI, API, MCP server
│   └── core/          # shared layer under the CLI, API and MCP server
├── tasks/             # benchmark tasks, one JSON file each
├── sandbox/           # Dockerfiles for the Python, Node, Go and Rust sandboxes
├── tests/             # pytest suite, including property-based tests
└── web/               # Next.js dashboard
```

## Development

The CLI (`cli.py`), the HTTP API (`api/main.py`) and the MCP server (`server.py`) are thin front ends. Each one parses its own input and formats its own output. Everything else goes in `src/polybench/core/`: the provider catalogue and construction, task selection, and planning, starting and reading back runs. Put new behaviour there, and all three front ends pick it up.

```bash
cd polybench
uv run pytest                  # tests
uv run ruff check . && uv run ruff format --check .
uv run mypy src                # strict type checking
pre-commit install             # run ruff and mypy on every commit
```

```bash
cd polybench/web
npm run lint && npm test && npm run build
```

CI runs all of these on every push and pull request to `main`.

## Contributing

Contributions are welcome, whether that's fixing a bug, adding a benchmark task or improving the dashboard.

- **Where to start:** the pinned issue [Start here: known issues and where to help](https://github.com/Jason-jo17/Polybench/issues/19) lists everything that's known to be broken or planned, in a suggested order.
- **Small first changes:** issues labelled [`good first issue`](https://github.com/Jason-jo17/Polybench/labels/good%20first%20issue).
- **How to contribute:** setup, checks and pull request guidelines are in [CONTRIBUTING.md](CONTRIBUTING.md).
- **Security problems** such as sandbox escapes: report privately, as described in [SECURITY.md](SECURITY.md).

**Project status:** the pipeline works end to end in all four languages, from the CLI, the dashboard, Docker Compose and MCP. Lint, strict type checks, the test suite (over 90% coverage) and `polybench tasks verify` all pass. The most useful contribution right now is more benchmark tasks ([#15](https://github.com/Jason-jo17/Polybench/issues/15)).

## License

[MIT](LICENSE)
