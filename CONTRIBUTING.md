# Contributing to PolyBench

Thanks for helping build PolyBench. This guide covers finding something to work on, setting up locally, and getting a pull request merged.

## Find something to work on

Start with the pinned issue, **[Start here: known issues and where to help](https://github.com/Jason-jo17/Polybench/issues/19)**. It lists every known problem and planned feature in a suggested order.

You can also filter issues by label:

| Label | Use it to find |
| --- | --- |
| [`good first issue`](https://github.com/Jason-jo17/Polybench/labels/good%20first%20issue) | small, well-scoped changes with clear instructions |
| [`help wanted`](https://github.com/Jason-jo17/Polybench/labels/help%20wanted) | bigger pieces of work where help is especially welcome |
| [`priority: high`](https://github.com/Jason-jo17/Polybench/labels/priority%3A%20high) | broken functionality or things blocking CI |
| `area: backend`, `area: dashboard`, `area: sandbox`, `area: tasks`, `area: ci`, `area: mcp` | the part of the project an issue touches |

**Comment on an issue before you start**, so nobody else works on the same thing. For large changes, such as anything in [#16](https://github.com/Jason-jo17/Polybench/issues/16), agree on the approach in the issue first.

If you find a problem that isn't listed, open an issue using a template. If it's a way to escape the sandbox, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

## Current state of CI

CI runs on every pull request to `main` and currently fails for reasons unrelated to most PRs. The failures are tracked in [#3](https://github.com/Jason-jo17/Polybench/issues/3), [#4](https://github.com/Jason-jo17/Polybench/issues/4), [#6](https://github.com/Jason-jo17/Polybench/issues/6), [#7](https://github.com/Jason-jo17/Polybench/issues/7) and [#8](https://github.com/Jason-jo17/Polybench/issues/8). Until they're fixed, reviewers check that **your PR doesn't add new failures**. Say in your PR description which checks were already failing.

## Set up locally

You'll need Python 3.11+, [uv](https://docs.astral.sh/uv/), Docker (running) and Node.js 20+.

### Backend

```bash
cd polybench
uv sync --all-extras --dev
cp .env.example .env               # add API keys only if you need a hosted provider
uv run polybench setup             # builds the Python, Node, Go and Rust sandbox images
pre-commit install                 # runs Ruff and mypy before each commit
uv run uvicorn polybench.api.main:app --reload --port 8080
```

The `mock` provider needs no API key and no network access, so it's the easiest way to exercise the whole pipeline.

### Dashboard

```bash
cd polybench/web
npm install
npm run dev                        # http://localhost:3000, proxies /api to port 8080
```

## Checks to run before opening a PR

Backend, from `polybench/`:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest --cov=polybench --cov-report=term-missing
```

Dashboard, from `polybench/web/`:

```bash
npm run lint
npx tsc --noEmit
npm run build
```

Tests must not need Docker or network access. Mock the sandbox and providers the way the existing tests in `polybench/tests/` do.

## Adding a benchmark task

Tasks are the easiest way to make PolyBench more useful, and you don't need to know the harness internals. See [#15](https://github.com/Jason-jo17/Polybench/issues/15) for ideas.

1. Copy an existing file from `polybench/tasks/<language>/`. Each task has `id`, `title`, `prompt`, `signature`, `test_code`, `difficulty`, `tags` and `timeout_seconds`.
2. Write the prompt so it states the requirements without giving away the solution.
3. Write hidden tests (`test_code`) that cover edge cases: empty input, duplicates, large input, invalid input.
4. Check that a correct reference solution passes and a plausible wrong one fails.
5. Run `uv run polybench tasks validate`.

Please send one task per pull request.

## Pull requests

- Branch from `main` and keep each PR focused on one issue.
- Write `Fixes #123` in the description so the issue closes when the PR merges.
- Explain what changed and how you tested it. For dashboard changes, include a screenshot.
- Add or update tests for behaviour changes.
- Don't add `# type: ignore` to silence mypy; fix the types instead.
- Keep formatting-only changes in a separate commit from logic changes.

## Code of conduct

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md). By taking part you agree to follow it.

## License

By contributing, you agree that your contributions are licensed under the project's [MIT License](LICENSE).
