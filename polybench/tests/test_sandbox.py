import pytest
import subprocess
from unittest.mock import MagicMock, call
from pathlib import Path
from polybench.schemas import Task, Language, Difficulty
from polybench.sandbox.runner import SandboxRunner, SandboxResult, _cleanup_containers, _active_containers

def test_sandbox_standard_language(mocker):
    # Mock subprocess.run
    mock_run = mocker.patch("subprocess.run")
    mock_proc = MagicMock()
    mock_proc.stdout = "pytest stdout"
    mock_proc.stderr = "pytest stderr"
    mock_proc.returncode = 0
    mock_run.return_value = mock_proc

    task = Task(
        id="python/test_task",
        language=Language.python,
        difficulty=Difficulty.easy,
        title="Standard Task",
        prompt="Write print(1)",
        signature="print(1)",
        test_code="assert True"
    )

    runner = SandboxRunner()
    res = runner.run("print(1)", task)

    assert res.exit_code == 0
    assert res.stdout == "pytest stdout"
    assert res.stderr == "pytest stderr"
    assert not res.timed_out
    assert res.runtime_ms >= 0

    # Verify that docker run was called with correct arguments
    calls = mock_run.call_args_list
    assert len(calls) == 1
    args, kwargs = calls[0]
    cmd = args[0]
    assert cmd[0] == "docker"
    assert cmd[1] == "run"
    assert "polybench-python:local" in cmd
    assert "test_solution.py" in cmd

def test_sandbox_unsupported_language_no_overrides():
    # Use a language with no built-in spec and no task-level overrides.
    task = Task(
        id="cobol/test_task",
        language="cobol",
        difficulty=Difficulty.easy,
        title="Unsupported Language",
        prompt="Write COBOL",
        signature="PROCEDURE DIVISION.",
        test_code="STOP RUN."
    )

    runner = SandboxRunner()
    with pytest.raises(ValueError) as excinfo:
        runner.run("PROCEDURE DIVISION. STOP RUN.", task)

    assert "requires custom sandbox spec fields" in str(excinfo.value)

def test_sandbox_custom_language_with_overrides(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_proc = MagicMock()
    mock_proc.stdout = "cargo test stdout"
    mock_proc.stderr = "cargo test stderr"
    mock_proc.returncode = 0
    mock_run.return_value = mock_proc

    task = Task(
        id="rust/test_task",
        language="rust",
        difficulty=Difficulty.easy,
        title="Custom Task",
        prompt="Write Rust",
        signature="fn main() {}",
        test_code="fn test() {}",
        image="polybench-rust:local",
        code_file="main.rs",
        test_file="test_main.rs",
        test_cmd=["cargo", "test"]
    )

    runner = SandboxRunner()
    res = runner.run("fn main() {}", task)

    assert res.exit_code == 0
    assert res.stdout == "cargo test stdout"
    assert res.stderr == "cargo test stderr"
    assert not res.timed_out

    # Verify the docker run args
    calls = mock_run.call_args_list
    assert len(calls) == 1
    args, _ = calls[0]
    cmd = args[0]
    assert "polybench-rust:local" in cmd
    assert cmd[-2:] == ["cargo", "test"]

def test_sandbox_timeout(mocker):
    # Mock subprocess.run to raise TimeoutExpired on the first run, and return success on the kill run
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        subprocess.TimeoutExpired(cmd=["docker", "run"], timeout=5, output=b"partial stdout", stderr=b"partial stderr"),
        MagicMock(returncode=0) # docker kill
    ]

    task = Task(
        id="python/timeout_task",
        language=Language.python,
        difficulty=Difficulty.easy,
        title="Timeout Task",
        prompt="loop forever",
        signature="while True: pass",
        test_code="pass",
        timeout_seconds=2
    )

    runner = SandboxRunner()
    res = runner.run("while True: pass", task)

    assert res.timed_out
    assert res.exit_code is None
    assert res.stdout == "partial stdout"
    assert res.stderr == "partial stderr"

    # Verify docker kill was called
    assert mock_run.call_count == 2
    kill_args, _ = mock_run.call_args_list[1]
    assert kill_args[0][0] == "docker"
    assert kill_args[0][1] == "kill"

def test_cleanup_containers(mocker):
    mock_run = mocker.patch("subprocess.run")
    _active_containers.clear()
    _active_containers.add("polybench-test-container")

    _cleanup_containers()

    assert len(_active_containers) == 0
    mock_run.assert_called_once_with(["docker", "kill", "polybench-test-container"], capture_output=True, check=False)
