import subprocess
import tempfile
import time
import uuid
import signal
import atexit
import sys
from pathlib import Path
from pydantic import BaseModel

from polybench.schemas import Task
from polybench.sandbox.policy import (
    NETWORK, MEMORY, CPUS, PIDS_LIMIT, READ_ONLY, TMPFS, USER, WALL_CLOCK_BUFFER_S, CAP_DROP
)

_MAX_OUTPUT_BYTES = 8 * 1024  # 8 KB cap per stream


def _trim(s: str) -> str:
    """Truncate output to _MAX_OUTPUT_BYTES, adding a marker at the cut point."""
    if len(s) <= _MAX_OUTPUT_BYTES:
        return s
    half = _MAX_OUTPUT_BYTES // 2
    dropped = len(s) - _MAX_OUTPUT_BYTES
    return s[:half] + f"\n...[{dropped} bytes truncated]...\n" + s[-half:]
from polybench.sandbox.languages import SPECS

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

class SandboxRunner:
    def run(self, code: str, task: Task) -> SandboxResult:
        """
        Security note: generated code is fully untrusted; it only ever runs inside the 
        container, never via exec/eval on the host.
        """
        # Dynamically construct spec if task provides overrides, otherwise fall back to SPECS
        if task.image and task.code_file and task.test_file and task.test_cmd:
            from polybench.sandbox.languages import ExecSpec
            spec = ExecSpec(
                image=task.image,
                code_file=task.code_file,
                test_file=task.test_file,
                test_cmd=task.test_cmd
            )
        else:
            from polybench.schemas import Language
            try:
                lang_enum = Language(task.language)
                spec = SPECS[lang_enum]
            except ValueError:
                raise ValueError(
                    f"Language '{task.language}' requires custom sandbox spec fields "
                    "(image, code_file, test_file, test_cmd) in the task JSON."
                )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            (tmp_path / spec.code_file).write_text(code, encoding="utf-8")
            (tmp_path / spec.test_file).write_text(task.test_code, encoding="utf-8")
            
            vol_name = f"polybench-vol-{uuid.uuid4().hex}"
            subprocess.run(["docker", "volume", "create", vol_name], check=True, capture_output=True)
            dummy_name = f"dummy-{vol_name}"
            subprocess.run(["docker", "create", "--name", dummy_name, "-v", f"{vol_name}:/workspace", "alpine"], check=True, capture_output=True)
            subprocess.run(["docker", "cp", f"{tmpdir}/.", f"{dummy_name}:/workspace"], check=True, capture_output=True)
            subprocess.run(["docker", "rm", "-f", dummy_name], check=True, capture_output=True)

            container_name = f"polybench-{uuid.uuid4().hex}"
            _active_containers.add(container_name)
            
            cmd = [
                "docker", "run", "--rm",
                "--name", container_name,
                "--network", NETWORK,
                "--memory", MEMORY,
                f"--cpus={CPUS}",
                "--pids-limit", str(PIDS_LIMIT),
                f"--user={USER}",
                f"--cap-drop={CAP_DROP}",
                "--security-opt=no-new-privileges:true",
                f"--tmpfs={TMPFS}",
                "-v", f"{vol_name}:/workspace:ro",
                "-w", "/workspace",
                "-e", "PYTEST_ADDOPTS=-p no:cacheprovider",
                "-e", "GOCACHE=/tmp/gocache",
                "-e", "TMPDIR=/tmp",
            ]
            if READ_ONLY:
                cmd.append("--read-only")
                
            cmd.append(spec.image)
            cmd.extend(spec.test_cmd)
            
            start_time = time.perf_counter()
            timed_out = False
            
            try:
                timeout_s = task.timeout_seconds + WALL_CLOCK_BUFFER_S
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout_s
                )
                stdout = proc.stdout
                stderr = proc.stderr
                exit_code = proc.returncode
            except subprocess.TimeoutExpired as e:
                timed_out = True
                stdout = e.stdout.decode("utf-8", "replace") if e.stdout else ""
                stderr = e.stderr.decode("utf-8", "replace") if e.stderr else ""
                exit_code = None
                subprocess.run(["docker", "kill", container_name], capture_output=True)
            finally:
                _active_containers.discard(container_name)
                subprocess.run(["docker", "volume", "rm", vol_name], capture_output=True)
            
            end_time = time.perf_counter()
            runtime_ms = int((end_time - start_time) * 1000)
            
            return SandboxResult(
                exit_code=exit_code,
                stdout=_trim(stdout),
                stderr=_trim(stderr),
                runtime_ms=runtime_ms,
                timed_out=timed_out
            )
