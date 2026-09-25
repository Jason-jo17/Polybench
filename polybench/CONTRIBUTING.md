# Contributing to PolyBench

Thank you for your interest in contributing to PolyBench! We welcome contributions from the community.

## Local Development Setup

PolyBench consists of a FastAPI backend and a Next.js frontend.

### Prerequisites
- Python 3.11+
- Node.js 20+
- Docker (for sandboxed task execution)
- `uv` (for Python dependency management)

### Backend Setup
1. Clone the repository and install dependencies using `uv`:
   ```bash
   uv sync --all-extras --dev
   ```
2. Install pre-commit hooks:
   ```bash
   pre-commit install
   ```
3. Copy `.env.example` to `.env` and fill in any required API keys.
4. Run the backend API server:
   ```bash
   uv run uvicorn polybench.api.main:app --reload --port 8080
   ```

### Frontend Setup
1. Navigate to the `web` directory:
   ```bash
   cd web
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Run the development server:
   ```bash
   npm run dev
   ```
4. Access the dashboard at `http://localhost:3000`.

### Building Sandboxes
Before running tasks, you need to build the Docker sandbox containers:
```bash
uv run polybench setup
```
This builds the Python, Node, Go and Rust images from `sandbox/`.

## Adding New Benchmark Tasks

1. Navigate to the `tasks/` directory.
2. Create a new JSON file following the schema (or see existing examples).
3. Ensure the task has a `prompt`, `signature`, and proper hidden `tests`.
4. Run task validation:
   ```bash
   uv run polybench tasks validate
   ```

## Pull Request Process

1. Fork the repository and create a new branch.
2. Make your changes, ensuring tests pass (`uv run pytest`).
3. Ensure code formatting is correct (we use Ruff and MyPy).
4. Submit a PR with a clear description of the changes.

## Code of Conduct
Please be respectful and constructive when communicating with other contributors.
