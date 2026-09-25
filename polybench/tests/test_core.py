"""Tests for polybench.core, the layer shared by the CLI, MCP server and API."""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from polybench.config import settings
from polybench.core import providers as core_providers
from polybench.core import runs as core_runs
from polybench.core.providers import (
    ALL_PROVIDERS,
    CLOUD_PROVIDERS,
    MissingApiKeyError,
    UnknownProviderError,
    check_provider,
    is_configured,
    make_provider,
)
from polybench.core.tasks import find_task, parse_tags, public_task, select_tasks
from polybench.db import get_session
from polybench.models import BenchmarkRun, Sample, TaskResult
from polybench.providers.mock_provider import MockProvider
from polybench.sandbox.runner import SandboxResult


@pytest.fixture
def no_keys(monkeypatch):
    for spec in CLOUD_PROVIDERS.values():
        monkeypatch.setattr(settings, spec.key_setting, None)


@pytest.fixture
def tasks_dir(tmp_path):
    d = tmp_path / "tasks"
    d.mkdir()
    for i, (lang, difficulty, tags) in enumerate(
        [
            ("python", "easy", ["strings"]),
            ("python", "hard", ["graphs", "search"]),
            ("go", "easy", ["strings"]),
        ]
    ):
        (d / f"t{i}.json").write_text(
            json.dumps(
                {
                    "id": f"{lang}/t{i}",
                    "language": lang,
                    "difficulty": difficulty,
                    "title": f"T{i}",
                    "prompt": "P",
                    "signature": "S",
                    "test_code": "SECRET TESTS",
                    "reference_solution": "SECRET SOLUTION",
                    "tags": tags,
                }
            )
        )
    return d


# ---------------------------------------------------------------------------
# providers
# ---------------------------------------------------------------------------


def test_every_cloud_provider_has_a_settings_field():
    for spec in CLOUD_PROVIDERS.values():
        assert hasattr(settings, spec.key_setting)


def test_unknown_provider_is_rejected():
    with pytest.raises(UnknownProviderError, match="Valid options"):
        check_provider("nope")


def test_cloud_provider_without_key_is_rejected(no_keys):
    with pytest.raises(MissingApiKeyError) as exc:
        make_provider("anthropic", "m", 0.2)
    assert exc.value.env_var == "ANTHROPIC_API_KEY"
    assert "ANTHROPIC_API_KEY not set" in str(exc.value)


def test_local_providers_need_no_key(no_keys):
    for name in ("mock", "ollama", "lmstudio"):
        check_provider(name)
        assert is_configured(name)
    assert not is_configured("openai")


def test_mock_provider(no_keys):
    assert isinstance(make_provider("mock", "demo", 0.0), MockProvider)


def test_anthropic_gets_the_key_from_settings(monkeypatch, mocker):
    """A key set only in .env (so only in settings, not os.environ) must still work."""
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-from-dotenv")
    client = mocker.patch("anthropic.Anthropic")
    make_provider("anthropic", "claude-x", 0.1)
    assert client.call_args.kwargs["api_key"] == "sk-ant-from-dotenv"


def test_openai_compatible_provider_uses_its_base_url(monkeypatch, mocker):
    monkeypatch.setattr(settings, "groq_api_key", "gsk-test")
    compat = mocker.patch("polybench.core.providers.OpenAICompatibleProvider")
    make_provider("groq", "llama", 0.3)
    assert compat.call_args.kwargs == {
        "api_key": "gsk-test",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama",
        "temperature": 0.3,
    }


def test_local_provider_uses_configured_base_url(monkeypatch, mocker):
    monkeypatch.setattr(settings, "lmstudio_base_url", "http://box:1234/v1")
    compat = mocker.patch("polybench.core.providers.OpenAICompatibleProvider")
    make_provider("lmstudio", "local-model", 0.0)
    assert compat.call_args.kwargs["base_url"] == "http://box:1234/v1"
    assert compat.call_args.kwargs["api_key"] == "lm-studio"


def test_all_providers_lists_cloud_and_local():
    assert set(ALL_PROVIDERS) == set(CLOUD_PROVIDERS) | {"mock", "ollama", "lmstudio"}
    assert core_providers.local_base_url("openai") is None


# ---------------------------------------------------------------------------
# tasks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        (" , ", None),
        ("a, b ,c", ["a", "b", "c"]),
        (["a", " b "], ["a", "b"]),
        ([], None),
    ],
)
def test_parse_tags(raw, expected):
    assert parse_tags(raw) == expected


def test_select_tasks_filters(tasks_dir):
    assert len(select_tasks(tasks_dir)) == 3
    assert {t.id for t in select_tasks(tasks_dir, lang="python")} == {
        "python/t0",
        "python/t1",
    }
    assert [t.id for t in select_tasks(tasks_dir, difficulty="hard")] == ["python/t1"]
    assert [t.id for t in select_tasks(tasks_dir, tags=["strings"], lang="go")] == [
        "go/t2"
    ]
    assert select_tasks(tasks_dir, lang="") == select_tasks(tasks_dir)


def test_select_tasks_rejects_unknown_difficulty(tasks_dir):
    with pytest.raises(ValueError):
        select_tasks(tasks_dir, difficulty="impossible")


def test_find_task(tasks_dir):
    task = find_task(tasks_dir, "go/t2")
    assert task is not None and task.language == "go"
    assert find_task(tasks_dir, "go/missing") is None


def test_public_task_never_exposes_hidden_fields(tasks_dir):
    task = select_tasks(tasks_dir)[0]
    for detail in (True, False):
        shown = public_task(task, detail=detail)
        text = json.dumps(shown)
        assert "SECRET" not in text
        assert "test_code" not in shown and "reference_solution" not in shown
    assert "prompt" in public_task(task)
    assert "prompt" not in public_task(task, detail=False)


# ---------------------------------------------------------------------------
# runs
# ---------------------------------------------------------------------------


def _plan(tasks_dir, **kw):
    return core_runs.plan_run(
        provider="mock", model="demo", tasks_dir=tasks_dir, samples=2, **kw
    )


def test_plan_run(tasks_dir):
    plan = _plan(tasks_dir, lang="python", difficulty="hard", tags=["graphs"])
    assert [t.id for t in plan.tasks] == ["python/t1"]
    assert plan.cfg.n == 2 and plan.cfg.lang == "python"
    assert plan.cfg.tags == ["graphs"]
    assert isinstance(plan.provider, MockProvider)


def test_plan_run_checks_the_provider_before_the_tasks(tasks_dir):
    with pytest.raises(UnknownProviderError):
        core_runs.plan_run(
            provider="nope", model="m", tasks_dir=tasks_dir, tags=["no-such-tag"]
        )


def test_plan_run_with_no_matching_tasks(tasks_dir):
    with pytest.raises(core_runs.NoTasksError):
        _plan(tasks_dir, tags=["no-such-tag"])


def test_start_run_records_a_pending_run(tmp_db, tasks_dir):
    plan = _plan(tasks_dir, lang="go")
    with get_session() as session:
        run = core_runs.start_run(session, plan)
        assert run.status == "PENDING"
        assert run.total_tasks == 1 and run.language_filter == "go"
        assert core_runs.active_run_count(session) == 1


def _passing_sandbox(mocker):
    fake = MagicMock()
    fake.run.return_value = SandboxResult(
        exit_code=0, stdout="ok", stderr="", runtime_ms=1, timed_out=False
    )
    mocker.patch("polybench.core.runs.SandboxRunner", return_value=fake)


def test_execute_run_completes_the_run(tmp_db, tasks_dir, mocker):
    _passing_sandbox(mocker)
    plan = _plan(tasks_dir, lang="python")
    with get_session() as session:
        run_id = core_runs.start_run(session, plan).id

    core_runs.execute_run(run_id, plan)

    with get_session() as session:
        run = session.get(BenchmarkRun, run_id)
        assert run is not None and run.status == "COMPLETED"
        results = core_runs.task_results(session, run_id)
        assert [r.task_id for r in results] == ["python/t0", "python/t1"]
        assert len(core_runs.run_samples(session, run_id)) == 4
        assert core_runs.active_run_count(session) == 0


def test_execute_run_marks_the_run_failed_on_error(tmp_db, tasks_dir, mocker):
    mocker.patch("polybench.core.runs.run_benchmark", side_effect=RuntimeError("boom"))
    mocker.patch("polybench.core.runs.SandboxRunner")
    plan = _plan(tasks_dir)
    with get_session() as session:
        run_id = core_runs.start_run(session, plan).id

    core_runs.execute_run(run_id, plan)  # must not raise

    with get_session() as session:
        run = session.get(BenchmarkRun, run_id)
        assert run is not None and run.status == "FAILED"


def _add_run(provider="mock", lang=None, status="COMPLETED", age_minutes=0) -> str:
    with get_session() as session:
        run = BenchmarkRun(
            model="m",
            provider=provider,
            language_filter=lang,
            samples_per_task=1,
            k=1,
            temperature=0.0,
            total_tasks=0,
            pass_at_k=0.0,
            status=status,
            created_at=datetime(2026, 1, 1) + timedelta(minutes=age_minutes),
        )
        session.add(run)
        session.commit()
        return run.id


def test_list_runs_is_newest_first_and_filters_before_limiting(tmp_db):
    old = _add_run(provider="openai", age_minutes=0)
    _add_run(provider="mock", age_minutes=1)
    _add_run(provider="mock", age_minutes=2)
    newest = _add_run(provider="openai", lang="go", age_minutes=3)
    with get_session() as session:
        assert [r.id for r in core_runs.list_runs(session, provider="openai")] == [
            newest,
            old,
        ]
        # The filter applies before the limit, so older matches aren't cut off.
        assert [
            r.id
            for r in core_runs.list_runs(session, limit=1, offset=1, provider="openai")
        ] == [old]
        assert [r.id for r in core_runs.list_runs(session, lang="go")] == [newest]


def test_mark_orphaned_runs_failed(tmp_db):
    pending = _add_run(status="PENDING")
    running = _add_run(status="RUNNING")
    done = _add_run(status="COMPLETED")
    with get_session() as session:
        assert core_runs.mark_orphaned_runs_failed(session) == 2
        assert core_runs.mark_orphaned_runs_failed(session) == 0
        runs = {rid: session.get(BenchmarkRun, rid) for rid in (pending, running, done)}
        statuses = {rid: run.status for rid, run in runs.items() if run is not None}
    assert statuses == {pending: "FAILED", running: "FAILED", done: "COMPLETED"}


def test_task_results_and_samples_are_scoped_to_the_run(tmp_db):
    a, b = _add_run(), _add_run()
    with get_session() as session:
        for run_id in (a, b):
            tr = TaskResult(
                run_id=run_id,
                task_id="python/t",
                language="python",
                difficulty="easy",
                samples_generated=1,
                samples_passed=1,
                task_pass_at_k=1.0,
            )
            session.add(tr)
            session.commit()
            session.add(
                Sample(task_result_id=tr.id, sample_index=0, raw_output="", passed=True)
            )
            session.commit()
        assert len(core_runs.task_results(session, a)) == 1
        assert len(core_runs.run_samples(session, a)) == 1


def test_preview_run_checks_the_provider_without_building_it(
    tasks_dir, mocker, monkeypatch
):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    build = mocker.patch("polybench.core.runs.make_provider")
    tasks = core_runs.preview_run(provider="openai", tasks_dir=tasks_dir, lang="go")
    assert [t.id for t in tasks] == ["go/t2"]
    build.assert_not_called()
    with pytest.raises(UnknownProviderError):
        core_runs.preview_run(provider="nope", tasks_dir=tasks_dir)
