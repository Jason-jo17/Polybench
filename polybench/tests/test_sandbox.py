import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from polybench.sandbox.policy import STARTUP_ALLOWANCE_S
from polybench.sandbox.runner import (
    SandboxRunner,
    _active_containers,
    _as_text,
    _cleanup_containers,
)
from polybench.schemas import Difficulty, Language, Task


class FakeDocker:
    """Stands in for subprocess.run and answers each docker command by its verb.

    `docker run` gets `run_result` (a CompletedProcess-like object, or an exception
    to raise). Files copied into the volume are captured at `docker cp` time,
    because the temporary directory is deleted afterwards.
    """

    def __init__(self, run_result=None, fail_on: str | None = None):
        self.run_result = run_result or MagicMock(stdout="ok", stderr="", returncode=0)
        self.fail_on = fail_on
        self.calls: list[list[str]] = []
        self.run_kwargs: dict = {}
        self.copied: dict[str, str] = {}

    def __call__(self, cmd, *args, **kwargs):
        self.calls.append(cmd)
        verb = " ".join(cmd[1:3]) if cmd[1] == "volume" else cmd[1]
        if verb == self.fail_on:
            raise subprocess.CalledProcessError(1, cmd)
        if verb == "cp":
            src = Path(cmd[2].rstrip(".").rstrip("/\\"))
            self.copied = {p.name: p.read_text(encoding="utf-8") for p in src.iterdir()}
        if verb == "run":
            self.run_kwargs = kwargs
            if isinstance(self.run_result, BaseException):
                raise self.run_result
            return self.run_result
        return MagicMock(returncode=0, stdout="", stderr="")

    def verbs(self) -> list[str]:
        return [" ".join(c[1:3]) if c[1] == "volume" else c[1] for c in self.calls]

    def run_cmd(self) -> list[str]:
        return next(c for c in self.calls if c[1] == "run")


def _task(language=Language.python, **extra) -> Task:
    return Task(
        id=f"{language}/t",
        language=language,
        difficulty=Difficulty.easy,
        title="T",
        prompt="P",
        signature="S",
        test_code="TEST CODE",
        timeout_seconds=7,
        **extra,
    )


def test_run_uses_isolation_flags_and_in_container_timeout(mocker):
    docker = FakeDocker(MagicMock(stdout="3 passed", stderr="", returncode=0))
    mocker.patch("subprocess.run", side_effect=docker)

    res = SandboxRunner().run("print(1)", _task())

    assert res.exit_code == 0 and res.stdout == "3 passed" and not res.timed_out
    cmd = docker.run_cmd()
    for flag in (
        "--network",
        "none",
        "--read-only",
        "--cap-drop=ALL",
        "--user=10001:10001",
    ):
        assert flag in cmd
    assert "--security-opt=no-new-privileges:true" in cmd
    assert any(f.startswith("--tmpfs=/tmp:") and "noexec" in f for f in cmd)
    # The task's limit applies to the tests only; start-up gets a separate allowance.
    image_at = cmd.index("polybench-python:local")
    assert cmd[image_at + 1 : image_at + 3] == ["timeout", "7"]
    assert cmd[-1] == "test_solution.py"
    assert docker.run_kwargs["timeout"] == 7 + STARTUP_ALLOWANCE_S
    # Only the code and the hidden tests are copied in, and nothing is left behind.
    assert docker.copied == {"solution.py": "print(1)", "test_solution.py": "TEST CODE"}
    assert docker.verbs()[-1] == "volume rm"
    assert not _active_containers


def test_go_gets_go_mod_and_an_executable_tmp(mocker):
    docker = FakeDocker()
    mocker.patch("subprocess.run", side_effect=docker)

    SandboxRunner().run("package solution", _task(Language.go))

    assert docker.copied["go.mod"].startswith("module solution")
    assert set(docker.copied) == {"go.mod", "solution.go", "solution_test.go"}
    tmpfs = next(f for f in docker.run_cmd() if f.startswith("--tmpfs="))
    assert "exec" in tmpfs and "noexec" not in tmpfs
    # Compilation runs first, outside the time limit; only the test binary is timed.
    shell, flag, script = docker.run_cmd()[-3:]
    assert (shell, flag) == ("sh", "-c")
    build, timed = script.split(" && exec ")
    assert "go test -c" in build
    assert timed == "timeout 7 /tmp/solution.test"


def test_task_level_sandbox_overrides(mocker):
    docker = FakeDocker(MagicMock(stdout="cargo out", stderr="cargo err", returncode=0))
    mocker.patch("subprocess.run", side_effect=docker)
    task = _task(
        "rust",
        image="custom-rust:latest",
        code_file="main.rs",
        test_file="test_main.rs",
        test_cmd=["cargo", "test"],
    )

    res = SandboxRunner().run("fn main() {}", task)

    assert (res.stdout, res.stderr) == ("cargo out", "cargo err")
    assert docker.run_cmd()[-5:] == [
        "custom-rust:latest",
        "timeout",
        "7",
        "cargo",
        "test",
    ]
    assert set(docker.copied) == {"main.rs", "test_main.rs"}


@pytest.mark.parametrize("exit_code", [124, 143])
def test_in_container_timeout_is_reported_as_timed_out(mocker, exit_code):
    docker = FakeDocker(MagicMock(stdout="", stderr="", returncode=exit_code))
    mocker.patch("subprocess.run", side_effect=docker)

    res = SandboxRunner().run("while True: pass", _task())

    assert res.timed_out and res.exit_code == exit_code


@pytest.mark.parametrize(
    "out, err", [(b"partial out", b"partial err"), ("partial out", "partial err")]
)
def test_stalled_container_is_killed_and_partial_output_kept(mocker, out, err):
    stall = subprocess.TimeoutExpired(
        cmd=["docker", "run"], timeout=1, output=out, stderr=err
    )
    docker = FakeDocker(stall)
    mocker.patch("subprocess.run", side_effect=docker)

    res = SandboxRunner().run("while True: pass", _task())

    assert res.timed_out and res.exit_code is None
    assert (res.stdout, res.stderr) == ("partial out", "partial err")
    assert "kill" in docker.verbs()
    assert docker.verbs()[-1] == "volume rm"


def test_setup_failure_still_cleans_up(mocker):
    docker = FakeDocker(fail_on="cp")
    mocker.patch("subprocess.run", side_effect=docker)

    with pytest.raises(subprocess.CalledProcessError):
        SandboxRunner().run("print(1)", _task())

    assert "run" not in docker.verbs()
    assert docker.verbs()[-2:] == ["rm", "volume rm"]


def test_unsupported_language_without_overrides_is_rejected():
    with pytest.raises(ValueError, match="requires custom sandbox spec fields"):
        SandboxRunner().run("PROCEDURE DIVISION.", _task("cobol"))


def test_as_text_accepts_bytes_str_and_none():
    assert _as_text(b"caf\xc3\xa9") == "café"
    assert _as_text("text") == "text"
    assert _as_text(None) == ""


def test_cleanup_containers(mocker):
    mock_run = mocker.patch("subprocess.run")
    _active_containers.clear()
    _active_containers.add("polybench-test-container")

    _cleanup_containers()

    assert len(_active_containers) == 0
    mock_run.assert_called_once_with(
        ["docker", "kill", "polybench-test-container"], capture_output=True, check=False
    )
