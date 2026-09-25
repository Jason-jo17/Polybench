import csv
import io
import json
import logging
import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from polybench import __version__
from polybench.config import PROJECT_ROOT, settings
from polybench.db import init_db, get_session
from polybench.engine import RunConfig, create_run, run_benchmark
from polybench.providers.base import LLMProvider
from polybench.providers.anthropic_provider import AnthropicProvider
from polybench.providers.mock_provider import MockProvider
from polybench.providers.openai_compatible import OpenAICompatibleProvider
from polybench.report.html import generate_report
from polybench.sandbox.runner import SandboxRunner
from polybench.schemas import Difficulty, Language, Task
from polybench.tasks.loader import load_tasks
from polybench.tasks.registry import TaskRegistry

app = typer.Typer(help="PolyBench AI Coding-Benchmark Harness")
tasks_app = typer.Typer(help="Manage tasks")
app.add_typer(tasks_app, name="tasks")

console = Console()

# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

# Maps provider name → (settings attribute name, env var name)
_PROVIDER_KEYS: dict[str, tuple[str, str]] = {
    "anthropic": ("anthropic_api_key", "ANTHROPIC_API_KEY"),
    "openai": ("openai_api_key", "OPENAI_API_KEY"),
    "groq": ("groq_api_key", "GROQ_API_KEY"),
    "together": ("together_api_key", "TOGETHER_API_KEY"),
    "mistral": ("mistral_api_key", "MISTRAL_API_KEY"),
    "deepseek": ("deepseek_api_key", "DEEPSEEK_API_KEY"),
    "xai": ("xai_api_key", "XAI_API_KEY"),
    "gemini": ("gemini_api_key", "GEMINI_API_KEY"),
    "fireworks": ("fireworks_api_key", "FIREWORKS_API_KEY"),
    "perplexity": ("perplexity_api_key", "PERPLEXITY_API_KEY"),
}

# OpenAI-compatible base URLs (all providers except anthropic)
_COMPAT_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "mistral": "https://api.mistral.ai/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "xai": "https://api.x.ai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "perplexity": "https://api.perplexity.ai",
}

# Default probe model per provider (for compass)
_COMPASS_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o",
    "groq": "llama-3.3-70b-versatile",
    "together": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "mistral": "mistral-small-latest",
    "deepseek": "deepseek-chat",
    "xai": "grok-3-mini",
    "gemini": "gemini-2.0-flash",
    "fireworks": "accounts/fireworks/models/llama-v3p3-70b-instruct",
    "perplexity": "sonar",
}


_LOCAL_PROVIDERS = {"mock", "ollama", "lmstudio"}
_ALL_PROVIDERS = set(_PROVIDER_KEYS) | _LOCAL_PROVIDERS


def _validate_provider(provider: str) -> None:
    """Exit with code 1 if provider name is not recognised."""
    if provider not in _ALL_PROVIDERS:
        valid = ", ".join(sorted(_ALL_PROVIDERS))
        console.print(
            f"[red]Unknown provider: {provider!r}. Valid options: {valid}[/red]"
        )
        raise typer.Exit(1)


def _get_api_key(provider: str) -> str | None:
    if provider not in _PROVIDER_KEYS:
        return None
    attr, _ = _PROVIDER_KEYS[provider]
    return getattr(settings, attr, None)


def _check_api_key(provider: str) -> None:
    """Exit with code 3 if a required API key is missing."""
    if provider in _LOCAL_PROVIDERS:
        return
    key = _get_api_key(provider)
    if not key:
        _, env_var = _PROVIDER_KEYS.get(provider, ("", f"{provider.upper()}_API_KEY"))
        console.print(
            f"[red]{env_var} not set — add it to .env or set the environment variable[/red]"
        )
        raise typer.Exit(3)


def _make_provider(provider: str, model: str, temperature: float) -> LLMProvider:
    if provider == "anthropic":
        return AnthropicProvider(model=model, temperature=temperature)
    if provider == "mock":
        return MockProvider(model=model, temperature=temperature)
    if provider == "ollama":
        return OpenAICompatibleProvider(
            api_key="ollama",
            base_url=settings.ollama_base_url,
            model=model,
            temperature=temperature,
        )
    if provider == "lmstudio":
        return OpenAICompatibleProvider(
            api_key="lm-studio",
            base_url=settings.lmstudio_base_url,
            model=model,
            temperature=temperature,
        )
    if provider in _COMPAT_BASE_URLS:
        return OpenAICompatibleProvider(
            api_key=_get_api_key(provider) or "",
            base_url=_COMPAT_BASE_URLS[provider],
            model=model,
            temperature=temperature,
        )
    console.print(f"[red]Unknown provider: {provider!r}[/red]")
    raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _check_docker() -> None:
    try:
        subprocess.run(["docker", "info"], check=True, capture_output=True)
    except Exception:
        console.print("[red]Docker unavailable[/red]")
        raise typer.Exit(4)


def _build_images() -> None:
    images = {
        "polybench-python:local": "Dockerfile.python",
        "polybench-node:local": "Dockerfile.node",
        "polybench-go:local": "Dockerfile.go",
        "polybench-rust:local": "Dockerfile.rust",
    }
    sandbox_dir = PROJECT_ROOT / "sandbox"
    for tag, dockerfile in images.items():
        res = subprocess.run(["docker", "image", "inspect", tag], capture_output=True)
        if res.returncode != 0:
            console.print(f"[yellow]Building {tag}…[/yellow]")
            build = subprocess.run(
                [
                    "docker",
                    "build",
                    "-t",
                    tag,
                    "-f",
                    str(sandbox_dir / dockerfile),
                    str(sandbox_dir),
                ],
            )
            if build.returncode != 0:
                console.print(
                    f"[red]Couldn't build {tag} from {sandbox_dir / dockerfile}. "
                    "See the Docker output above.[/red]"
                )
                raise typer.Exit(1)
            console.print(f"[green]Built {tag}[/green]")


def _setup_logging(log_file: Path | None) -> None:
    if log_file is None:
        return
    import logging.handlers

    handler = logging.handlers.RotatingFileHandler(
        str(log_file),
        maxBytes=5 * 1024 * 1024,  # 5 MB per file
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger = logging.getLogger("polybench")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.info("PolyBench CLI started")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command("version")
def version_cmd() -> None:
    """Print PolyBench version."""
    console.print(f"polybench {__version__}")


@app.command("setup")
def setup() -> None:
    """Check and build all sandbox Docker images."""
    _check_docker()
    console.print("[cyan]Setting up sandbox environments…[/cyan]")
    _build_images()
    console.print("[green]Setup complete.[/green]")


@app.command("keys")
def keys_cmd() -> None:
    """Show which provider API keys are configured."""
    table = Table("Provider", "Env Variable", "Status", "Type")

    for provider, (attr, env_var) in _PROVIDER_KEYS.items():
        key = getattr(settings, attr, None)
        if key:
            masked = key[:4] + "..." + key[-4:] if len(key) > 8 else "****"
            status = f"[green]OK  {masked}[/green]"
        else:
            status = "[red]--  not set[/red]"
        table.add_row(provider, env_var, status, "cloud")

    table.add_row(
        "ollama",
        "(no key - uses base URL)",
        f"[cyan]{settings.ollama_base_url}[/cyan]",
        "local",
    )
    table.add_row(
        "lmstudio",
        "(no key - uses base URL)",
        f"[cyan]{settings.lmstudio_base_url}[/cyan]",
        "local",
    )
    table.add_row("mock", "(built-in)", "[cyan]always available[/cyan]", "built-in")

    console.print(table)
    console.print(
        "[dim]To configure: add keys to .env in the polybench directory, or set environment variables.[/dim]"
    )


@app.command("run")
def run(
    model: str = typer.Option(settings.polybench_default_model, help="Model name"),
    provider: str = typer.Option(
        "anthropic",
        help="Provider: anthropic|openai|groq|together|mistral|deepseek|xai|gemini|fireworks|perplexity|ollama|lmstudio|mock",
    ),
    tasks: Path = typer.Option(
        Path(settings.polybench_tasks_dir), help="Tasks directory"
    ),
    lang: str = typer.Option(None, help="Language filter"),
    difficulty: Difficulty = typer.Option(None, help="Difficulty filter"),
    tags: str = typer.Option(None, help="Comma-separated tag filter (all must match)"),
    samples: int = typer.Option(5, "--samples", "-n", help="Samples per task"),
    k: int = typer.Option(1, "-k", help="k in pass@k"),
    temperature: float = typer.Option(0.2, help="Sampling temperature"),
    db: str = typer.Option(settings.polybench_db, help="SQLite DB path"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview tasks without running"
    ),
    log_file: Path = typer.Option(
        None, "--log-file", help="Append run log to this file"
    ),
) -> None:
    """Run a benchmark."""
    _setup_logging(log_file)
    _validate_provider(provider)
    _check_api_key(provider)

    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    loaded = list(load_tasks(tasks))
    registry = TaskRegistry(loaded)
    filtered = registry.filter(lang=lang, difficulty=difficulty, tags=tag_list)
    if not filtered:
        console.print("[red]No tasks match the given filters[/red]")
        raise typer.Exit(2)

    if dry_run:
        table = Table("ID", "Language", "Difficulty", "Tags", title="Dry-run preview")
        for t in filtered:
            table.add_row(t.id, t.language, t.difficulty.value, ", ".join(t.tags))
        console.print(table)
        console.print(
            f"[cyan]{len(filtered)} tasks × {samples} samples = {len(filtered) * samples} LLM calls[/cyan]"
        )
        return

    _check_docker()
    _build_images()

    llm = _make_provider(provider, model, temperature)
    runner = SandboxRunner()
    cfg = RunConfig(model, provider, samples, k, temperature, lang, tag_list)

    init_db(db)
    with get_session() as session:
        pending = create_run(session, cfg, filtered)
        run_record = run_benchmark(pending.id, cfg, filtered, llm, runner, session)
        if run_record is None:
            console.print(
                f"[red]Run {pending.id} could not be loaded from the database[/red]"
            )
            raise typer.Exit(1)
        run_id = run_record.id
        run_pass_at_k = run_record.pass_at_k

    log = logging.getLogger("polybench")
    log.info(
        "Run complete id=%s pass_at_k=%.4f provider=%s model=%s",
        run_id,
        run_pass_at_k,
        provider,
        model,
    )

    console.print(f"[green]Run complete! ID: {run_id}[/green]")
    console.print(f"Overall Pass@{k}: {run_pass_at_k:.4f}")


@tasks_app.command("list")
def tasks_list(
    tasks: Path = typer.Option(
        Path(settings.polybench_tasks_dir), help="Tasks directory"
    ),
    lang: str = typer.Option(None, help="Language filter"),
    difficulty: Difficulty = typer.Option(None, help="Difficulty filter"),
    tags: str = typer.Option(None, help="Comma-separated tag filter"),
) -> None:
    """List all tasks."""
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    loaded = list(load_tasks(tasks))
    registry = TaskRegistry(loaded)
    filtered = registry.filter(lang=lang, difficulty=difficulty, tags=tag_list)

    table = Table("ID", "Language", "Difficulty", "Tags")
    for t in filtered:
        table.add_row(t.id, t.language, t.difficulty.value, ", ".join(t.tags))
    console.print(table)


@tasks_app.command("validate")
def tasks_validate(
    tasks: Path = typer.Option(
        Path(settings.polybench_tasks_dir), help="Tasks directory"
    ),
) -> None:
    """Validate all task JSON files."""
    try:
        loaded = list(load_tasks(tasks))
        console.print(f"[green]Validated {len(loaded)} tasks successfully.[/green]")
    except Exception as exc:
        console.print(f"[red]Validation failed:[/red] {exc}")
        raise typer.Exit(1)


@app.command("report")
def report(
    run_id: str = typer.Option(..., help="Run ID"),
    db: str = typer.Option(settings.polybench_db, help="SQLite DB path"),
    out: Path = typer.Option(Path("./report.html"), help="Output HTML path"),
) -> None:
    """Generate an HTML report for a completed run."""
    init_db(db)
    with get_session() as session:
        try:
            generate_report(session, run_id, str(out))
            console.print(f"[green]Report written to {out}[/green]")
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1)


@app.command("compare")
def compare(
    run_a: str = typer.Option(..., help="First run ID"),
    run_b: str = typer.Option(..., help="Second run ID"),
    db: str = typer.Option(settings.polybench_db, help="SQLite DB path"),
) -> None:
    """Compare pass@k for two runs side-by-side."""
    from polybench.models import BenchmarkRun, TaskResult
    from sqlmodel import select

    init_db(db)
    with get_session() as session:
        a_rows = session.exec(
            select(TaskResult).where(TaskResult.run_id == run_a)
        ).all()
        b_rows = session.exec(
            select(TaskResult).where(TaskResult.run_id == run_b)
        ).all()
        run_a_rec = session.get(BenchmarkRun, run_a)
        run_b_rec = session.get(BenchmarkRun, run_b)
        label_a = run_a_rec.model if run_a_rec else run_a[:8]
        label_b = run_b_rec.model if run_b_rec else run_b[:8]

    a_map = {r.task_id: r.task_pass_at_k for r in a_rows}
    b_map = {r.task_id: r.task_pass_at_k for r in b_rows}

    table = Table("Task ID", f"A: {label_a}", f"B: {label_b}", "Delta")
    for task_id in sorted(set(a_map) | set(b_map)):
        va, vb = a_map.get(task_id, 0.0), b_map.get(task_id, 0.0)
        delta = vb - va
        color = "green" if delta > 0 else ("red" if delta < 0 else "dim")
        table.add_row(
            task_id, f"{va:.2f}", f"{vb:.2f}", f"[{color}]{delta:+.2f}[/{color}]"
        )
    console.print(table)


@app.command("history")
def history(
    db: str = typer.Option(settings.polybench_db, help="SQLite DB path"),
    limit: int = typer.Option(20, help="Maximum number of runs to show"),
    provider: str = typer.Option(None, help="Filter by provider"),
    lang: str = typer.Option(None, help="Filter by language_filter"),
) -> None:
    """List past benchmark runs."""
    from polybench.models import BenchmarkRun
    from sqlmodel import select

    init_db(db)
    with get_session() as session:
        stmt = (
            select(BenchmarkRun).order_by(BenchmarkRun.created_at.desc()).limit(limit)
        )  # type: ignore[attr-defined]
        runs = session.exec(stmt).all()

    if not runs:
        console.print("[dim]No runs found.[/dim]")
        return

    table = Table(
        "Run ID", "Model", "Provider", "Lang", "Tasks", "n", "Pass@k", "Created"
    )
    for r in runs:
        if provider and r.provider != provider:
            continue
        if lang and r.language_filter != lang:
            continue
        table.add_row(
            r.id[:12],
            r.model,
            r.provider,
            r.language_filter or "all",
            str(r.total_tasks),
            str(r.samples_per_task),
            f"{r.pass_at_k:.2%}",
            str(r.created_at)[:16],
        )
    console.print(table)


@app.command("export")
def export(
    run_id: str = typer.Option(..., help="Run ID to export"),
    db: str = typer.Option(settings.polybench_db, help="SQLite DB path"),
    format: str = typer.Option("json", help="Output format: json|csv"),
    out: Path = typer.Option(None, help="Output file (default: stdout)"),
) -> None:
    """Export task results for a run to JSON or CSV."""
    from polybench.models import BenchmarkRun, TaskResult, Sample
    from sqlmodel import select

    init_db(db)
    with get_session() as session:
        run = session.get(BenchmarkRun, run_id)
        if run is None:
            console.print(f"[red]Run {run_id!r} not found[/red]")
            raise typer.Exit(1)
        results = session.exec(
            select(TaskResult).where(TaskResult.run_id == run_id)
        ).all()
        samples = session.exec(
            select(Sample).join(TaskResult).where(TaskResult.run_id == run_id)
        ).all()

    rows = []
    sample_map: dict[str, list[Sample]] = {}
    for s in samples:
        sample_map.setdefault(s.task_result_id, []).append(s)

    for r in results:
        for s in sample_map.get(r.id, []):
            rows.append(
                {
                    "run_id": run_id,
                    "model": run.model,
                    "provider": run.provider,
                    "task_id": r.task_id,
                    "language": r.language,
                    "difficulty": r.difficulty,
                    "sandbox_image": r.sandbox_image,
                    "sample_index": s.sample_index,
                    "passed": s.passed,
                    "failure_kind": s.failure_kind,
                    "exit_code": s.exit_code,
                    "runtime_ms": s.runtime_ms,
                    "timed_out": s.timed_out,
                    "input_tokens": s.input_tokens,
                    "output_tokens": s.output_tokens,
                    "task_pass_at_k": r.task_pass_at_k,
                }
            )

    if format == "json":
        text = json.dumps(rows, indent=2, default=str)
    elif format == "csv":
        buf = io.StringIO()
        if rows:
            writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        text = buf.getvalue()
    else:
        console.print("[red]Unknown format. Use json or csv.[/red]")
        raise typer.Exit(1)

    if out:
        out.write_text(text, encoding="utf-8")
        console.print(f"[green]Exported {len(rows)} rows to {out}[/green]")
    else:
        console.print(text)


@app.command("compass")
def compass(
    db: str = typer.Option(settings.polybench_db, help="SQLite DB path"),
) -> None:
    """Check connectivity for all configured providers (AI Compass Flow)."""
    table = Table("Provider", "Model", "Status", "Detail")
    any_fail = False

    _colors = {
        "PASS": "green",
        "FAIL": "red",
        "WARN": "yellow",
        "SKIP": "dim",
        "LOCAL": "cyan",
    }

    def _styled(s: str) -> str:
        return f"[{_colors.get(s, 'white')}]{s}[/{_colors.get(s, 'white')}]"

    # Cloud providers
    for provider_name, probe_model in _COMPASS_MODELS.items():
        key = _get_api_key(provider_name)
        if not key:
            table.add_row(
                provider_name, probe_model, _styled("SKIP"), "API key not configured"
            )
            continue
        try:
            p = _make_provider(provider_name, probe_model, 0.0)
            res = p.generate("Reply with exactly: OK")
            if "ok" in res.raw_output.lower():
                status, detail = "PASS", f"responded in {res.runtime_ms}ms"
            else:
                status, detail = "WARN", f"unexpected reply: {res.raw_output[:60]}"
        except Exception as exc:
            status, detail = "FAIL", str(exc)[:80]
            any_fail = True
        table.add_row(provider_name, probe_model, _styled(status), detail)

    # Local providers
    import urllib.request
    import urllib.error

    for provider_name, base_url in [
        ("ollama", settings.ollama_base_url),
        ("lmstudio", settings.lmstudio_base_url),
    ]:
        try:
            urllib.request.urlopen(base_url.rstrip("/") + "/models", timeout=2)
            status, detail = "LOCAL", f"reachable at {base_url}"
        except urllib.error.URLError:
            status, detail = "SKIP", f"offline ({base_url})"
        except Exception as exc:
            status, detail = "SKIP", str(exc)[:60]
        table.add_row(provider_name, "(any)", _styled(status), detail)

    table.add_row("mock", "demo-v1", _styled("PASS"), "always available")

    console.print(table)
    if any_fail:
        raise typer.Exit(1)


@app.command("sandbox-test")
def sandbox_test() -> None:
    """Test that the sandbox enforces isolation (network, FS, PID limits)."""
    _check_docker()
    _build_images()
    runner = SandboxRunner()

    console.print("Probing outbound network isolation…")
    t1 = Task(
        id="test/net",
        language=Language.python,
        difficulty=Difficulty.easy,
        title="net",
        prompt="",
        signature="",
        test_code="pass",
        timeout_seconds=2,
    )
    res1 = runner.run(
        "import urllib.request; urllib.request.urlopen('http://1.1.1.1', timeout=1)", t1
    )
    if res1.exit_code == 0:
        console.print("[red]Network isolation FAILED[/red]")
        raise typer.Exit(1)
    console.print("[green]Network: blocked[/green]")

    console.print("Probing FS write isolation…")
    t2 = Task(
        id="test/fs",
        language=Language.python,
        difficulty=Difficulty.easy,
        title="fs",
        prompt="",
        signature="",
        test_code="pass",
    )
    res2 = runner.run("open('/workspace/out.txt', 'w').write('x')", t2)
    if res2.exit_code == 0:
        console.print("[red]FS isolation FAILED[/red]")
        raise typer.Exit(1)
    console.print("[green]FS: blocked[/green]")

    console.print("Probing PID limit (fork bomb)…")
    t3 = Task(
        id="test/pids",
        language=Language.python,
        difficulty=Difficulty.easy,
        title="pids",
        prompt="",
        signature="",
        test_code="pass",
        timeout_seconds=3,
    )
    runner.run("import os\nwhile True:\n    try: os.fork()\n    except: break", t3)
    console.print("[green]PID: survived[/green]")

    console.print("[green]All isolation guarantees hold.[/green]")


@app.command("health")
def health(
    db: str = typer.Option(settings.polybench_db, help="SQLite DB path"),
) -> None:
    """Check system health: database, Docker images, and provider keys."""
    from polybench.models import BenchmarkRun
    from sqlmodel import select, func

    all_ok = True

    # Database
    try:
        init_db(db)
        with get_session() as session:
            count = session.exec(select(func.count()).select_from(BenchmarkRun)).one()  # type: ignore[call-overload]
        console.print(f"[green]DB[/green]       OK — {count} run(s) at {db}")
    except Exception as exc:
        console.print(f"[red]DB[/red]       ERROR — {exc}")
        all_ok = False

    # Docker + images
    try:
        subprocess.run(["docker", "info"], check=True, capture_output=True)
        console.print("[green]Docker[/green]   available")
        for img in [
            "polybench-python:local",
            "polybench-node:local",
            "polybench-go:local",
            "polybench-rust:local",
        ]:
            res = subprocess.run(
                ["docker", "image", "inspect", img], capture_output=True
            )
            status = (
                "[green]built[/green]"
                if res.returncode == 0
                else "[yellow]not built — run 'polybench setup'[/yellow]"
            )
            console.print(f"  {img}: {status}")
    except Exception:
        console.print(
            "[red]Docker[/red]   unavailable — install Docker and start the daemon"
        )
        all_ok = False

    # Provider keys
    configured = sum(
        1 for attr, _ in _PROVIDER_KEYS.values() if getattr(settings, attr, None)
    )
    total = len(_PROVIDER_KEYS)
    console.print(
        f"[green]Keys[/green]     {configured}/{total} cloud providers configured"
    )

    if all_ok:
        console.print("[green]System healthy.[/green]")
    else:
        console.print("[red]System has issues — see above.[/red]")
        raise typer.Exit(1)


@app.command("backup")
def backup(
    db: str = typer.Option(settings.polybench_db, help="SQLite DB path"),
    out: Path = typer.Option(
        None, help="Destination file (default: <db>.bak.<timestamp>)"
    ),
) -> None:
    """Create a timestamped backup copy of the SQLite database."""
    import shutil
    from datetime import datetime

    src = Path(db)
    if not src.exists():
        console.print(f"[red]Database not found: {src}[/red]")
        raise typer.Exit(1)

    if out is None:
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        out = src.with_suffix(f".bak.{ts}.db")

    shutil.copy2(src, out)
    console.print(f"[green]Backed up {src} → {out}[/green]")
