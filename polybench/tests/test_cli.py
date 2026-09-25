import json
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from polybench.cli import app
from polybench.models import BenchmarkRun, TaskResult

runner = CliRunner()


@pytest.fixture
def sample_task_json(tmp_path):
    t_dir = tmp_path / "tasks"
    t_dir.mkdir()
    (t_dir / "t1.json").write_text(
        json.dumps(
            {
                "id": "python/test_task",
                "language": "python",
                "difficulty": "easy",
                "title": "T",
                "prompt": "P",
                "signature": "S",
                "test_code": "code",
            }
        )
    )
    return t_dir


# ---------------------------------------------------------------------------
# tasks subcommands
# ---------------------------------------------------------------------------


def test_cli_tasks_list(sample_task_json):
    res = runner.invoke(app, ["tasks", "list", "--tasks", str(sample_task_json)])
    assert res.exit_code == 0
    assert "python/test_task" in res.stdout


def test_cli_tasks_list_tag_filter(sample_task_json):
    res = runner.invoke(
        app,
        ["tasks", "list", "--tasks", str(sample_task_json), "--tags", "nonexistent"],
    )
    assert res.exit_code == 0


def test_cli_tasks_validate_success(sample_task_json):
    res = runner.invoke(app, ["tasks", "validate", "--tasks", str(sample_task_json)])
    assert res.exit_code == 0
    assert "1" in res.stdout  # "Validated 1 tasks"


def test_cli_tasks_validate_fail(tmp_path):
    t_dir = tmp_path / "tasks"
    t_dir.mkdir()
    (t_dir / "t1.json").write_text("invalid json")
    res = runner.invoke(app, ["tasks", "validate", "--tasks", str(t_dir)])
    assert res.exit_code == 1
    assert "validation failed" in res.stdout.lower()


# ---------------------------------------------------------------------------
# run command
# ---------------------------------------------------------------------------


def _run_args(tasks_dir, db):
    return [
        "run",
        "--provider",
        "mock",
        "--tasks",
        str(tasks_dir),
        "--db",
        str(db),
        "--samples",
        "2",
        "-k",
        "1",
    ]


def test_cli_run_passes_the_new_run_id_to_the_engine(mocker, sample_task_json, tmp_db):
    mocker.patch("polybench.cli._check_docker")
    mocker.patch("polybench.cli._build_images")
    mock_run_benchmark = mocker.patch("polybench.cli.run_benchmark")
    mock_record = MagicMock()
    mock_record.id = "run-abc"
    mock_record.pass_at_k = 0.95
    mock_run_benchmark.return_value = mock_record

    res = runner.invoke(app, _run_args(sample_task_json, tmp_db))

    assert res.exit_code == 0, res.stdout
    assert "run-abc" in res.stdout
    run_id, cfg, tasks, *_ = mock_run_benchmark.call_args.args
    assert isinstance(run_id, str) and run_id
    assert cfg.n == 2 and cfg.provider == "mock"
    assert [t.id for t in tasks] == ["python/test_task"]


def test_cli_run_end_to_end_with_fake_sandbox(mocker, sample_task_json, tmp_db):
    """Runs the real engine; only Docker is replaced. Regression test for #3."""
    from sqlmodel import Session, create_engine, select

    from polybench.sandbox.runner import SandboxResult

    mocker.patch("polybench.cli._check_docker")
    mocker.patch("polybench.cli._build_images")
    fake_runner = MagicMock()
    fake_runner.run.return_value = SandboxResult(
        exit_code=0, stdout="1 passed", stderr="", runtime_ms=5, timed_out=False
    )
    mocker.patch("polybench.cli.SandboxRunner", return_value=fake_runner)

    res = runner.invoke(app, _run_args(sample_task_json, tmp_db))

    assert res.exit_code == 0, res.stdout
    assert "Run complete" in res.stdout
    with Session(create_engine(f"sqlite:///{tmp_db}")) as session:
        run = session.exec(select(BenchmarkRun)).one()
        result = session.exec(select(TaskResult)).one()
    assert run.status == "COMPLETED"
    assert run.total_tasks == 1 and run.samples_per_task == 2
    assert run.pass_at_k == 1.0
    assert result.samples_passed == 2


def test_cli_run_reports_missing_run_record(mocker, sample_task_json, tmp_db):
    mocker.patch("polybench.cli._check_docker")
    mocker.patch("polybench.cli._build_images")
    mocker.patch("polybench.cli.run_benchmark", return_value=None)

    res = runner.invoke(app, _run_args(sample_task_json, tmp_db))

    assert res.exit_code == 1
    assert "could not be loaded" in res.stdout


def test_cli_run_dry_run(sample_task_json):
    res = runner.invoke(
        app,
        [
            "run",
            "--provider",
            "mock",
            "--tasks",
            str(sample_task_json),
            "--dry-run",
        ],
    )
    assert res.exit_code == 0
    assert "python/test_task" in res.stdout


def test_cli_run_docker_unavailable(mocker, sample_task_json, tmp_db):
    mocker.patch("subprocess.run", side_effect=Exception("docker not found"))
    res = runner.invoke(
        app,
        [
            "run",
            "--provider",
            "mock",
            "--tasks",
            str(sample_task_json),
            "--db",
            str(tmp_db),
        ],
    )
    assert res.exit_code == 4


def test_cli_run_invalid_provider(mocker, sample_task_json, tmp_db):
    mocker.patch("subprocess.run", return_value=MagicMock(returncode=0))
    res = runner.invoke(
        app,
        [
            "run",
            "--provider",
            "invalid_provider",
            "--tasks",
            str(sample_task_json),
            "--db",
            str(tmp_db),
        ],
    )
    assert res.exit_code == 1


def test_cli_run_no_matching_tasks(mocker, sample_task_json, tmp_db):
    res = runner.invoke(
        app,
        [
            "run",
            "--provider",
            "mock",
            "--tasks",
            str(sample_task_json),
            "--lang",
            "rust",
            "--dry-run",
        ],
    )
    assert res.exit_code == 2


def test_cli_run_missing_anthropic_key(mocker, sample_task_json, tmp_db):
    mocker.patch("polybench.cli.settings.anthropic_api_key", None)
    res = runner.invoke(
        app,
        [
            "run",
            "--provider",
            "anthropic",
            "--tasks",
            str(sample_task_json),
            "--db",
            str(tmp_db),
        ],
    )
    assert res.exit_code == 3


# ---------------------------------------------------------------------------
# report / compare
# ---------------------------------------------------------------------------


def test_cli_report(mocker, tmp_db, tmp_path):
    mocker.patch("polybench.cli.generate_report")
    out_file = tmp_path / "report.html"
    res = runner.invoke(
        app,
        [
            "report",
            "--run-id",
            "test-run",
            "--db",
            str(tmp_db),
            "--out",
            str(out_file),
        ],
    )
    assert res.exit_code == 0


def test_cli_report_error(mocker, tmp_db, tmp_path):
    mocker.patch(
        "polybench.cli.generate_report", side_effect=ValueError("Run not found")
    )
    out_file = tmp_path / "report.html"
    res = runner.invoke(
        app,
        [
            "report",
            "--run-id",
            "test-run",
            "--db",
            str(tmp_db),
            "--out",
            str(out_file),
        ],
    )
    assert res.exit_code == 1
    assert "run not found" in res.stdout.lower()


def test_cli_compare(mocker, tmp_db):
    mock_session = MagicMock()
    mocker.patch(
        "polybench.cli.get_session",
        return_value=MagicMock(__enter__=MagicMock(return_value=mock_session)),
    )
    res_a = [TaskResult(run_id="a", task_id="t1", task_pass_at_k=1.0)]
    res_b = [TaskResult(run_id="b", task_id="t1", task_pass_at_k=0.5)]
    mock_session.exec.return_value.all.side_effect = [res_a, res_b]
    mock_session.get.return_value = None

    res = runner.invoke(
        app, ["compare", "--run-a", "a", "--run-b", "b", "--db", str(tmp_db)]
    )
    assert res.exit_code == 0
    assert "t1" in res.stdout


# ---------------------------------------------------------------------------
# history / export
# ---------------------------------------------------------------------------


def test_cli_history_empty(tmp_db):
    res = runner.invoke(app, ["history", "--db", str(tmp_db)])
    assert res.exit_code == 0
    assert "No runs" in res.stdout


def test_cli_history_with_runs(tmp_db):
    from polybench.db import get_session

    run = BenchmarkRun(
        model="mock-model",
        provider="mock",
        samples_per_task=1,
        k=1,
        temperature=0.2,
        total_tasks=1,
        pass_at_k=1.0,
    )
    with get_session() as session:
        session.add(run)
        session.commit()

    res = runner.invoke(app, ["history", "--db", str(tmp_db)])
    assert res.exit_code == 0
    assert "mock-model" in res.stdout


def test_cli_export_json(tmp_db, tmp_path):
    from polybench.db import get_session
    from polybench.models import TaskResult, Sample

    run = BenchmarkRun(
        model="m",
        provider="mock",
        samples_per_task=1,
        k=1,
        temperature=0.0,
        total_tasks=1,
        pass_at_k=1.0,
    )
    with get_session() as session:
        session.add(run)
        session.commit()
        tr = TaskResult(
            run_id=run.id,
            task_id="python/t",
            language="python",
            difficulty="easy",
            samples_generated=1,
            samples_passed=1,
            task_pass_at_k=1.0,
        )
        session.add(tr)
        session.commit()
        s = Sample(
            task_result_id=tr.id,
            sample_index=0,
            raw_output="```python\npass\n```",
            extracted_code="pass",
            passed=True,
            failure_kind=None,
            exit_code=0,
            stdout="",
            stderr="",
            runtime_ms=5,
            timed_out=False,
        )
        session.add(s)
        session.commit()
        run_id = run.id

    out = tmp_path / "out.json"
    res = runner.invoke(
        app,
        [
            "export",
            "--run-id",
            run_id,
            "--db",
            str(tmp_db),
            "--format",
            "json",
            "--out",
            str(out),
        ],
    )
    assert res.exit_code == 0
    data = json.loads(out.read_text())
    assert len(data) == 1
    assert data[0]["task_id"] == "python/t"


def test_cli_export_csv(tmp_db, tmp_path):
    from polybench.db import get_session
    from polybench.models import TaskResult, Sample

    run = BenchmarkRun(
        model="m",
        provider="mock",
        samples_per_task=1,
        k=1,
        temperature=0.0,
        total_tasks=1,
        pass_at_k=1.0,
    )
    with get_session() as session:
        session.add(run)
        session.commit()
        tr = TaskResult(
            run_id=run.id,
            task_id="python/t",
            language="python",
            difficulty="easy",
            samples_generated=1,
            samples_passed=1,
            task_pass_at_k=1.0,
        )
        session.add(tr)
        session.commit()
        s = Sample(
            task_result_id=tr.id,
            sample_index=0,
            raw_output="x",
            extracted_code="x",
            passed=True,
            failure_kind=None,
            exit_code=0,
            stdout="",
            stderr="",
            runtime_ms=5,
            timed_out=False,
        )
        session.add(s)
        session.commit()
        run_id = run.id

    out = tmp_path / "out.csv"
    res = runner.invoke(
        app,
        [
            "export",
            "--run-id",
            run_id,
            "--db",
            str(tmp_db),
            "--format",
            "csv",
            "--out",
            str(out),
        ],
    )
    assert res.exit_code == 0
    assert "task_id" in out.read_text()


def test_cli_export_not_found(tmp_db):
    res = runner.invoke(app, ["export", "--run-id", "nonexistent", "--db", str(tmp_db)])
    assert res.exit_code == 1


def test_cli_export_bad_format(tmp_db):
    from polybench.db import get_session

    run = BenchmarkRun(
        model="m",
        provider="mock",
        samples_per_task=1,
        k=1,
        temperature=0.0,
        total_tasks=1,
        pass_at_k=1.0,
    )
    with get_session() as session:
        session.add(run)
        session.commit()
        run_id = run.id
    res = runner.invoke(
        app, ["export", "--run-id", run_id, "--db", str(tmp_db), "--format", "xml"]
    )
    assert res.exit_code == 1


# ---------------------------------------------------------------------------
# sandbox-test
# ---------------------------------------------------------------------------


def test_cli_sandbox_test(mocker):
    mocker.patch("subprocess.run", return_value=MagicMock(returncode=0))
    mock_sandbox = MagicMock()
    mocker.patch("polybench.cli.SandboxRunner", return_value=mock_sandbox)
    # Network blocked (exit 1), FS blocked (exit 1), PID survived (exit 0)
    mock_sandbox.run.side_effect = [
        MagicMock(exit_code=1),  # net probe: non-zero = isolated ✓
        MagicMock(exit_code=1),  # FS probe: non-zero = isolated ✓
        MagicMock(exit_code=0),  # PID probe: any result is OK
    ]
    res = runner.invoke(app, ["sandbox-test"])
    assert res.exit_code == 0, res.stdout
    assert "all isolation guarantees hold" in res.stdout.lower()


def test_cli_sandbox_test_net_fail(mocker):
    mocker.patch("subprocess.run", return_value=MagicMock(returncode=0))
    mock_sandbox = MagicMock()
    mocker.patch("polybench.cli.SandboxRunner", return_value=mock_sandbox)
    # Network succeeds (exit 0) = isolation failure
    mock_sandbox.run.side_effect = [MagicMock(exit_code=0)]
    res = runner.invoke(app, ["sandbox-test"])
    assert res.exit_code == 1
    assert "network isolation failed" in res.stdout.lower()


# ---------------------------------------------------------------------------
# compass
# ---------------------------------------------------------------------------


def test_cli_compass_no_keys(mocker):
    mocker.patch("polybench.cli.settings.anthropic_api_key", None)
    mocker.patch("polybench.cli.settings.openai_api_key", None)
    res = runner.invoke(app, ["compass"])
    assert res.exit_code == 0
    assert "SKIP" in res.stdout


def test_cli_compass_anthropic_pass(mocker):
    mocker.patch("polybench.cli.settings.anthropic_api_key", "sk-test")
    mocker.patch("polybench.cli.settings.openai_api_key", None)
    mock_prov = MagicMock()
    mock_prov.generate.return_value = MagicMock(raw_output="OK", runtime_ms=42)
    mocker.patch("polybench.cli.AnthropicProvider", return_value=mock_prov)
    res = runner.invoke(app, ["compass"])
    assert res.exit_code == 0
    assert "PASS" in res.stdout


def test_cli_compass_provider_fail(mocker):
    mocker.patch("polybench.cli.settings.anthropic_api_key", "sk-bad")
    mocker.patch("polybench.cli.settings.openai_api_key", None)
    mock_prov = MagicMock()
    mock_prov.generate.side_effect = Exception("auth error")
    mocker.patch("polybench.cli.AnthropicProvider", return_value=mock_prov)
    res = runner.invoke(app, ["compass"])
    assert res.exit_code == 1
    assert "FAIL" in res.stdout


def test_cli_compass_openai_pass(mocker):
    mocker.patch("polybench.cli.settings.anthropic_api_key", None)
    mocker.patch("polybench.cli.settings.openai_api_key", "sk-oai-test")
    mock_prov = MagicMock()
    mock_prov.generate.return_value = MagicMock(raw_output="OK", runtime_ms=30)
    mocker.patch("polybench.cli.OpenAICompatibleProvider", return_value=mock_prov)
    res = runner.invoke(app, ["compass"])
    assert res.exit_code == 0
    assert "PASS" in res.stdout


# ---------------------------------------------------------------------------
# sandbox image builds
# ---------------------------------------------------------------------------


def _docker_images(mocker, labels: dict[str, str | None], build_rc: int = 0):
    """Fake `docker image inspect` / `docker build`; returns the list of built tags."""
    built: list[str] = []

    def fake_run(cmd, *args, **kwargs):
        if cmd[1:3] == ["image", "inspect"]:
            label = labels.get(cmd[-1])
            return MagicMock(returncode=1 if label is None else 0, stdout=label or "")
        if cmd[1] == "build":
            built.append(cmd[cmd.index("-t") + 1])
            return MagicMock(returncode=build_rc)
        raise AssertionError(cmd)

    mocker.patch("polybench.cli.subprocess.run", side_effect=fake_run)
    return built


def test_build_images_skips_up_to_date_and_rebuilds_changed(mocker):
    import hashlib

    from polybench.cli import _build_images
    from polybench.config import PROJECT_ROOT

    def sha(name):
        return hashlib.sha256(
            (PROJECT_ROOT / "sandbox" / name).read_bytes()
        ).hexdigest()

    built = _docker_images(
        mocker,
        {
            "polybench-python:local": sha("Dockerfile.python"),  # up to date
            "polybench-node:local": "stale-hash",  # Dockerfile changed
            "polybench-go:local": None,  # missing
            "polybench-rust:local": sha("Dockerfile.rust"),
        },
    )

    _build_images()

    assert built == ["polybench-node:local", "polybench-go:local"]


def test_build_images_exits_cleanly_when_docker_build_fails(mocker):
    import typer

    from polybench.cli import _build_images

    _docker_images(mocker, {}, build_rc=1)
    with pytest.raises(typer.Exit):
        _build_images()
