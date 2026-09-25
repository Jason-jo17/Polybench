from unittest.mock import MagicMock

from typer.testing import CliRunner

from polybench.cli import app
from polybench.config import PROJECT_ROOT
from polybench.sandbox.runner import SandboxResult
from polybench.schemas import Difficulty, Language, Task
from polybench.tasks.loader import load_tasks
from polybench.tasks.verify import verify_task

PASS = SandboxResult(
    exit_code=0, stdout="1 passed", stderr="", runtime_ms=1, timed_out=False
)
FAIL = SandboxResult(
    exit_code=1,
    stdout="FAILED test_x - AssertionError",
    stderr="",
    runtime_ms=1,
    timed_out=False,
)


def _task(reference="def f(): return 1") -> Task:
    return Task(
        id="python/t",
        language=Language.python,
        difficulty=Difficulty.easy,
        title="T",
        prompt="P",
        signature="def f(): ...",
        test_code="from solution import f\ndef test(): assert f() == 1",
        reference_solution=reference,
    )


def _runner(results: dict[str, SandboxResult]) -> MagicMock:
    runner = MagicMock()
    runner.run.side_effect = lambda code, task: results[code]
    return runner


def test_sound_task_is_ok():
    runner = _runner({"def f(): return 1": PASS, "def f(): ...": FAIL})
    assert verify_task(_task(), runner).ok


def test_failing_reference_is_reported_with_its_output():
    runner = _runner({"def f(): return 1": FAIL, "def f(): ...": FAIL})
    res = verify_task(_task(), runner)
    assert not res.ok
    assert "reference solution fails" in res.problem and "wrong_output" in res.problem
    assert "AssertionError" in res.output


def test_tests_that_the_bare_signature_passes_are_reported():
    runner = _runner({"def f(): return 1": PASS, "def f(): ...": PASS})
    res = verify_task(_task(), runner)
    assert not res.ok and "check too little" in res.problem


def test_missing_reference_is_reported_without_running_anything():
    runner = MagicMock()
    res = verify_task(_task(reference=None), runner)
    assert not res.ok and "no reference_solution" in res.problem
    runner.run.assert_not_called()


def test_every_bundled_task_has_a_reference_solution():
    tasks = list(load_tasks(PROJECT_ROOT / "tasks"))
    assert tasks
    assert [t.id for t in tasks if not t.reference_solution] == []


def test_verify_command_reports_problems_and_exits_nonzero(mocker, tmp_path):
    import json

    (tmp_path / "t.json").write_text(json.dumps(_task().model_dump(mode="json")))
    mocker.patch("polybench.cli._check_docker")
    mocker.patch("polybench.cli._build_images")
    mocker.patch(
        "polybench.cli.SandboxRunner",
        return_value=_runner({"def f(): return 1": FAIL, "def f(): ...": FAIL}),
    )

    res = CliRunner().invoke(app, ["tasks", "verify", "--tasks", str(tmp_path)])

    assert res.exit_code == 1
    assert "python/t" in res.stdout and "1 of 1 tasks have problems" in res.stdout


def test_verify_command_succeeds_when_all_tasks_are_sound(mocker, tmp_path):
    import json

    (tmp_path / "t.json").write_text(json.dumps(_task().model_dump(mode="json")))
    mocker.patch("polybench.cli._check_docker")
    mocker.patch("polybench.cli._build_images")
    mocker.patch(
        "polybench.cli.SandboxRunner",
        return_value=_runner({"def f(): return 1": PASS, "def f(): ...": FAIL}),
    )

    res = CliRunner().invoke(app, ["tasks", "verify", "--tasks", str(tmp_path)])

    assert res.exit_code == 0, res.stdout
    assert "All 1 tasks verified" in res.stdout
