# PolyBench

PolyBench measures how well large language models write working code. It sends programming tasks to a model, extracts the generated code, runs it in an isolated Docker sandbox against a hidden test suite, and scores the results with pass@k plus a failure taxonomy (extraction failed, compile error, runtime error, wrong output, timeout, memory exceeded, security violation).

It includes 21 tasks in Python, JavaScript, Go and Rust, and supports Anthropic, OpenAI, OpenAI-compatible providers, and local models through Ollama or LM Studio.

## Install

```bash
uv sync --all-extras --dev
cp .env.example .env        # add the API keys you plan to use
uv run polybench setup      # builds the sandbox images (needs Docker)
```

## Use

```bash
uv run polybench run --provider mock --model demo --dry-run
uv run polybench run --provider anthropic --model claude-sonnet-4-6 -n 5 -k 1
uv run polybench history
uv run polybench report --run-id RUN_ID --out report.html
```

The package also provides a FastAPI backend (`polybench.api.main:app`) for the web dashboard in `web/`, and an MCP server (`polybench-mcp`) for AI agents.

pass@k uses the unbiased estimator `pass@k = 1 − C(n − c, k) / C(n, k)`, or `1.0` when `n − c < k`.

Full documentation, including the dashboard, Docker Compose, MCP setup and configuration, is in the [repository README](https://github.com/Jason-jo17/Polybench#readme).

## License

MIT. See [LICENSE](https://github.com/Jason-jo17/Polybench/blob/main/LICENSE).
