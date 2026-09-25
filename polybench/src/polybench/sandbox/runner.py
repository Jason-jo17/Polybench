import atexit
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from pydantic import BaseModel

from polybench.sandbox.languages import SPECS, ExecSpec
from polybench.sandbox.policy import (
    CAP_DROP,
    CPUS,
    MEMORY,
    NETWORK,
    PIDS_LIMIT,
    READ_ONLY,
    STARTUP_ALLOWANCE_S,
    TIMEOUT_EXIT_CODES,
    TMPFS,
    USER,
)
from polybench.schemas import Language, Task

_MAX_OUTPUT_BYTES = 8 * 1024  # 8 KB cap per stream


def _trim(s: str) -> str:
    """Truncate output to _MAX_OUTPUT_BYTES, adding a marker at the cut point."""
    if len(s) <= _MAX_OUTPUT_BYTES:
        return s
    half = _MAX_OUTPUT_BYTES // 2
    dropped = len(s) - _MAX_OUTPUT_BYTES
    return s[:half] + f"\n...[{dropped} bytes truncated]...\n" + s[-half:]


def _as_text(data: str | bytes | None) -> str:
    """TimeoutExpired carries partial output as bytes or str depending on platform."""
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", "replace")
    return data


# Global registry of active container names for cleanup on interrupt or exit
_active_containers: set[str] = set()


def _cleanup_containers() -> None:
    if not _active_containers:
        return
    containers = list(_active_containers)
    for name in containers:
        try:
            subprocess.run(["docker", "kill", name], capture_output=True, check=False)
        except Exception:
            pass
        _active_containers.discard(name)


def _signal_handler(signum: int, frame: object) -> None:
    _cleanup_containers()
    sys.exit(128 + signum)


# Register cleanups
atexit.register(_cleanup_containers)
try:
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
except (ValueError, OSError):
    pass


class SandboxResult(BaseModel):
    exit_code: int | None
    stdout: str
    stderr: str
    runtime_ms: int
    timed_out: bool


def _spec_for(task: Task) -> ExecSpec:
    """Use the task's own sandbox fields if it has them, otherwise the language default."""
    if task.image and task.code_file and task.test_file and task.test_cmd:
        return ExecSpec(
            image=task.image,
            code_file=task.code_file,
            test_file=task.test_file,
            test_cmd=task.test_cmd,
        )
    try:
        return SPECS[Language(task.language)]
    except ValueError:
        raise ValueError(
            f"Language '{task.language}' requires custom sandbox spec fields "
            "(image, code_file, test_file, test_cmd) in the task JSON."
        )


def build_run_command(
    container_name: str, volume: str, spec: ExecSpec, timeout_seconds: int
) -> list[str]:
    """The `docker run` command for one sample. The task's time limit is enforced
    inside the container with `timeout` around the tests only, so neither container
    start-up nor compilation counts against the code being tested."""
    cmd = [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        "--network",
        NETWORK,
        "--memory",
        MEMORY,
        f"--cpus={CPUS}",
        "--pids-limit",
        str(PIDS_LIMIT),
        f"--user={USER}",
        f"--cap-drop={CAP_DROP}",
        "--security-opt=no-new-privileges:true",
        f"--tmpfs={spec.tmpfs or TMPFS}",
        "-v",
        f"{volume}:/workspace:ro",
        "-w",
        "/workspace",
        "-e",
        "PYTEST_ADDOPTS=-p no:cacheprovider",
        "-e",
        "GOCACHE=/tmp/gocache",
        "-e",
        "GOFLAGS=-vet=off",
        "-e",
        "TMPDIR=/tmp",
    ]
    if READ_ONLY:
        cmd.append("--read-only")
    cmd.append(spec.image)
    timed = ["timeout", str(timeout_seconds), *spec.test_cmd]
    if spec.build:
        cmd += ["sh", "-c", f"{spec.build} && exec {shlex.join(timed)}"]
    else:
        cmd += timed
    return cmd


class SandboxRunner:
    def run(self, code: str, task: Task) -> SandboxResult:
        """
        Security note: generated code is fully untrusted; it only ever runs inside the
        container, never via exec/eval on the host.
        """
        spec = _spec_for(task)
        volume = f"polybench-vol-{uuid.uuid4().hex}"
        loader = f"polybench-load-{uuid.uuid4().hex}"
        container_name = f"polybench-{uuid.uuid4().hex}"

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                (tmp_path / spec.code_file).write_text(code, encoding="utf-8")
                (tmp_path / spec.test_file).write_text(task.test_code, encoding="utf-8")
                for name, content in spec.extra_files.items():
                    (tmp_path / name).write_text(content, encoding="utf-8")

                # Copy the files into a fresh volume through a stopped container that
                # is never started. This avoids bind-mounting a host directory.
                subprocess.run(
                    ["docker", "volume", "create", volume],
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    [
                        "docker",
                        "create",
                        "--name",
                        loader,
                        "-v",
                        f"{volume}:/workspace",
                        spec.image,
                    ],
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    ["docker", "cp", f"{tmpdir}/.", f"{loader}:/workspace"],
                    check=True,
                    capture_output=True,
                )
                subprocess.run(["docker", "rm", "-f", loader], capture_output=True)

            cmd = build_run_command(container_name, volume, spec, task.timeout_seconds)
            _active_containers.add(container_name)
            start_time = time.perf_counter()
            timed_out = False
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=task.timeout_seconds + STARTUP_ALLOWANCE_S,
                )
                stdout, stderr, exit_code = proc.stdout, proc.stderr, proc.returncode
                if exit_code in TIMEOUT_EXIT_CODES:
                    timed_out = True
            except subprocess.TimeoutExpired as e:
                # The container itself hung (e.g. Docker stalled); kill it.
                timed_out = True
                stdout, stderr, exit_code = _as_text(e.stdout), _as_text(e.stderr), None
                subprocess.run(["docker", "kill", container_name], capture_output=True)
            runtime_ms = int((time.perf_counter() - start_time) * 1000)
        finally:
            _active_containers.discard(container_name)
            subprocess.run(["docker", "rm", "-f", loader], capture_output=True)
            subprocess.run(
                ["docker", "volume", "rm", "-f", volume], capture_output=True
            )

        return SandboxResult(
            exit_code=exit_code,
            stdout=_trim(stdout),
            stderr=_trim(stderr),
            runtime_ms=runtime_ms,
            timed_out=timed_out,
        )
