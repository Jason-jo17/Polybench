# PolyBench

PolyBench is a polyglot AI coding-benchmark harness. It sends real-world programming tasks to frontier LLMs (Claude, GPT), extracts the generated code, executes it inside a hardened sandbox against a hidden test suite, and scores model performance using `pass@k` plus a structured failure taxonomy. It supports Python, JavaScript, and Go tasks and emits both terminal and HTML evaluation reports.

## Architecture

```
[ LLM Provider ] --> [ Extract Code ] --> [ Docker Sandbox ] --> [ Scoring ] --> [ Report ]
```

### Security Model
The sandbox is completely isolated. Generated code runs in a Docker container without host mounts (except read-only code injection), no network access, strict memory and CPU limits, and dropped privileges. Generated/untrusted code is never executed via `exec` or `eval` on the host.

### Pass@k
Model performance is evaluated using the unbiased `pass@k` estimator:
`pass@k = 1 - C(n - c, k) / C(n, k)` when `(n - c) >= k`, else `1.0`.

## Quickstart

### Local Development (Manual Setup)

1. **Initialize backend project using uv**:
   ```bash
   uv sync --all-extras --dev
   ```
2. **Install pre-commit hooks**:
   ```bash
   pre-commit install
   ```
3. **Build sandbox containers**:
   ```bash
   docker build -t polybench-python:local -f sandbox/Dockerfile.python sandbox/
   # Repeat for node, go
   ```
4. **Run backend server**:
   ```bash
   uv run uvicorn polybench.api.main:app --reload
   ```
5. **Run frontend (Next.js)**:
   ```bash
   cd web
   npm install
   npm run dev
   ```
   Access the dashboard at `http://localhost:3000`.

### Production Deployment (Docker Compose)

To run the entire stack (Database, Backend, Frontend) via Docker Compose:
```bash
docker-compose up -d --build
```
Access the application at `http://localhost:3000`.

### AI Agent Connectivity (MCP)

PolyBench includes a fully compliant Model Context Protocol (MCP) server. To connect it to your AI agent (like Claude Desktop), add the following to your MCP configuration (e.g., `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "polybench": {
      "command": "uv",
      "args": ["run", "python", "-m", "polybench.server"],
      "cwd": "/absolute/path/to/polybench"
    }
  }
}
```
