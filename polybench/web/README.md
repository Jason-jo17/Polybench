# PolyBench dashboard

The web interface for PolyBench: start benchmark runs, inspect each task and sample, and compare runs. It's a Next.js app that talks to the PolyBench FastAPI backend.

## Running it

Start the API first (from `polybench/`):

```bash
uv run uvicorn polybench.api.main:app --port 8080
```

Then start the dashboard:

```bash
npm install
npm run dev
```

Open http://localhost:3000.

Requests to `/api/*` are proxied to the backend (see `next.config.ts`). The backend defaults to `http://127.0.0.1:8080`. Set `POLYBENCH_API_URL` to point somewhere else. Rewrites are resolved at build time, so set it before `npm run build`.

If `POLYBENCH_DASHBOARD_PASSWORD` is set, the dashboard asks for it through HTTP basic auth (see `src/proxy.ts`). Any username works. It's read at server start, so the same build works with or without a password.

## Scripts

| Command | What it does |
| --- | --- |
| `npm run dev` | development server with hot reload |
| `npm run build` | production build (standalone output, used by `Dockerfile.frontend`) |
| `npm start` | serve the production build |
| `npm run lint` | ESLint |

See the [repository README](../../README.md) for the rest of the project.
