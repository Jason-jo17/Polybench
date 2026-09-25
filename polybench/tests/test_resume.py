import json
import sqlite3
import threading
from unittest.mock import MagicMock

from sqlmodel import select
from typer.testing import CliRunner

from polybench.cli import app
from polybench.config import settings
from polybench.db import get_session, init_db
from polybench.engine import RunConfig, config_from_run, create_run, run_benchmark
from polybench.models import BenchmarkRun, Sample, TaskResult
from polybench.providers.mock_provider import MockProvider
from polybench.sandbox.runner import SandboxResult
from polybench.schemas import Difficulty, Language, Task

PASS = SandboxResult(
    exit_code=0, stdout="1 passed", stderr="", runtime_ms=1, timed_out=False
)


def _task() -> Task:
    return Task(
        id="python/t",
        language=Language.python,
        difficulty=Difficulty.easy,
        title="T",
        prompt="P",
        signature="def f(): ...",
        test_code="def test(): pass",
        tags=["a", "b"],
    )


def _cfg(n=3) -> RunConfig:
    return RunConfig(
        model="m",
        provider="mock",
        n=n,
        k=1,
        temperature=0.2,
        lang="python",
        tags=["a", "b"],
    )


def _interrupted_run(session, n=3, stored_passes=(True,)) -> str:
    """A RUNNING run whose first samples were stored before it was interrupted."""
    run = create_run(session, _cfg(n), [_task()])
    run.status = "RUNNING"
    tr = TaskResult(
        run_id=run.id,
        task_id="python/t",
        language="python",
        difficulty="easy",
        samples_generated=len(stored_passes),
        samples_passed=sum(stored_passes),
        task_pass_at_k=0.0,
    )
    session.add(run)
    session.add(tr)
    session.commit()
    for i, passed in enumerate(stored_passes):
        session.add(
            Sample(task_result_id=tr.id, sample_index=i, raw_output="", passed=passed)
        )
    session.commit()
    return run.id


def test_resume_only_runs_missing_samples_and_keeps_stored_ones(tmp_db):
    runner = MagicMock()
    runner.run.return_value = SandboxResult(
        exit_code=1,
        stdout="FAILED x - AssertionError",
        stderr="",
        runtime_ms=1,
        timed_out=False,
    )
    with get_session() as session:
        run_id = _interrupted_run(session, n=3, stored_passes=(True,))
        run_benchmark(
            run_id, _cfg(3), [_task()], MockProvider("perfect"), runner, session
        )

        assert runner.run.call_count == 2  # samples 1 and 2 only
        tr = session.exec(select(TaskResult).where(TaskResult.run_id == run_id)).one()
        samples = session.exec(
            select(Sample).where(Sample.task_result_id == tr.id)
        ).all()
        run = session.get(BenchmarkRun, run_id)
    assert sorted(s.sample_index for s in samples) == [0, 1, 2]
    assert (tr.samples_generated, tr.samples_passed) == (3, 1)
    assert run.status == "COMPLETED"
    assert abs(run.pass_at_k - 1 / 3) < 1e-9


def test_scores_are_written_while_the_run_is_in_progress(tmp_db, monkeypatch):
    monkeypatch.setattr(settings, "polybench_sandbox_workers", 1)
    seen: list[tuple[int, int]] = []

    def run(code, task):
        # Read what another client would see before this sample is recorded.
        with get_session() as other:
            tr = other.exec(select(TaskResult)).one()
            seen.append((tr.samples_generated, tr.samples_passed))
        return PASS

    runner = MagicMock()
    runner.run.side_effect = run
    with get_session() as session:
        run_record = create_run(session, _cfg(3), [_task()])
        run_benchmark(
            run_record.id, _cfg(3), [_task()], MockProvider("perfect"), runner, session
        )
    assert seen == [(0, 0), (1, 1), (2, 2)]


def test_config_round_trips_through_the_stored_run(tmp_db):
    with get_session() as session:
        run = create_run(session, _cfg(4), [_task()])
        cfg = config_from_run(run)
    assert (cfg.model, cfg.provider, cfg.n, cfg.k, cfg.lang) == (
        "m",
        "mock",
        4,
        1,
        "python",
    )
    assert cfg.tags == ["a", "b"]


def _run_threads_inline(monkeypatch):
    class Inline:
        def __init__(self, target, args=(), daemon=None):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(threading, "Thread", Inline)


def test_api_start_resumes_interrupted_runs(tmp_db, monkeypatch):
    import polybench.api.main as api

    with get_session() as session:
        run_id = _interrupted_run(session)
    calls = []
    monkeypatch.setattr(
        api, "execute_benchmark_run", lambda rid, cfg, *a: calls.append((rid, cfg.n))
    )
    monkeypatch.setattr(settings, "polybench_resume_runs", True)
    _run_threads_inline(monkeypatch)

    api._handle_interrupted_runs()

    assert calls == [(run_id, 3)]


def test_api_start_can_mark_interrupted_runs_failed_instead(tmp_db, monkeypatch):
    import polybench.api.main as api

    with get_session() as session:
        run_id = _interrupted_run(session)
    monkeypatch.setattr(settings, "polybench_resume_runs", False)

    api._handle_interrupted_runs()

    with get_session() as session:
        assert session.get(BenchmarkRun, run_id).status == "FAILED"


def test_cli_resume_finishes_an_interrupted_run(tmp_db, tmp_path, mocker):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "t.json").write_text(json.dumps(_task().model_dump(mode="json")))
    with get_session() as session:
        run_id = _interrupted_run(session, n=3, stored_passes=(True,))
    mocker.patch("polybench.cli._check_docker")
    mocker.patch("polybench.cli._build_images")
    runner = MagicMock()
    runner.run.return_value = PASS
    mocker.patch("polybench.cli.SandboxRunner", return_value=runner)

    res = CliRunner().invoke(
        app, ["resume", run_id, "--tasks", str(tasks_dir), "--db", str(tmp_db)]
    )

    assert res.exit_code == 0, res.stdout
    assert runner.run.call_count == 2
    assert "Run complete" in res.stdout


def test_cli_resume_reports_unknown_and_completed_runs(tmp_db):
    res = CliRunner().invoke(app, ["resume", "nope", "--db", str(tmp_db)])
    assert res.exit_code == 2 and "No run with ID" in res.stdout

    with get_session() as session:
        run = create_run(session, _cfg(), [_task()])
        run.status = "COMPLETED"
        session.add(run)
        session.commit()
        run_id = run.id
    res = CliRunner().invoke(app, ["resume", run_id, "--db", str(tmp_db)])
    assert res.exit_code == 0 and "already complete" in res.stdout


def test_old_databases_gain_new_nullable_columns(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "create table benchmarkrun (id varchar primary key, created_at datetime,"
        " model varchar not null, provider varchar not null, language_filter varchar,"
        " samples_per_task integer not null, k integer not null, temperature float not null,"
        " total_tasks integer not null, pass_at_k float not null, status varchar not null,"
        " git_sha varchar)"
    )
    conn.execute(
        "insert into benchmarkrun values"
        " ('r1', '2026-01-01', 'm', 'mock', null, 1, 1, 0.2, 1, 0.5, 'COMPLETED', null)"
    )
    conn.commit()
    conn.close()

    init_db(str(path))

    with get_session() as session:
        run = session.get(BenchmarkRun, "r1")
        assert run.model == "m" and run.tag_filter is None
