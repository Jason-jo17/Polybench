from enum import StrEnum


class FailureKind(StrEnum):
    EXTRACTION_FAILED = "extraction_failed"
    COMPILE_ERROR = "compile_error"
    RUNTIME_ERROR = "runtime_error"
    WRONG_OUTPUT = "wrong_output"
    TIMEOUT = "timeout"
    MEMORY_EXCEEDED = "memory_exceeded"
    SECURITY_VIOLATION = "security_violation"


def classify(
    exit_code: int | None,
    stdout: str,
    stderr: str,
    timed_out: bool,
) -> FailureKind | None:
    """Return the failure kind for a sandbox run, or None if the run passed."""
    if timed_out:
        return FailureKind.TIMEOUT

    # OOM: Docker sends SIGKILL (exit 137) or stderr contains OOM markers.
    if exit_code == 137 or "OOM" in stderr or "out of memory" in stderr.lower():
        return FailureKind.MEMORY_EXCEEDED

    if exit_code == 0:
        return None  # passed

    # --- Compile / syntax errors ---
    _compile_signals = (
        # Python
        "SyntaxError",
        # Node.js — syntax errors print to stderr
        "SyntaxError:",
        # Go
        "build failed",
        "undefined:",
        "cannot use",
        "declared and not used",
        "imported and not used",
        "has no field or method",
        "[solution.test]",  # header `go test -c` prints before any compile error
        # Rust
        "error[E",
        "error: aborting",
        # Generic
        "compile error",
        "syntax error",
    )
    if any(sig in stderr for sig in _compile_signals):
        return FailureKind.COMPILE_ERROR
    # Test runners report these on stdout (pytest collection errors, Node's TAP
    # output, `go test` build failures). Only unambiguous signals are used here,
    # because test failure messages also go to stdout. A missing required name
    # means the code doesn't match the signature, so it counts as not compiling.
    _compile_signals_stdout = (
        "SyntaxError",
        "[build failed]",
        "error[E",
        "cannot import name",
        "does not provide an export named",
        "SyntaxError: Named export",
    )
    if any(sig in stdout for sig in _compile_signals_stdout):
        return FailureKind.COMPILE_ERROR

    # --- Security / sandbox violations ---
    _security_signals = (
        "network is unreachable",
        "operation not permitted",
        "permission denied",
        "read-only file system",
    )
    if any(sig in stderr.lower() for sig in _security_signals):
        return FailureKind.SECURITY_VIOLATION

    # --- Wrong output / assertion failures ---
    _wrong_signals_stderr = ("AssertionError", "FAIL", "--- FAIL:")
    _wrong_signals_stdout = (
        "AssertionError",
        "FAILED",  # pytest: "FAILED test_solution.py::test_name"
        "FAIL",  # Go summary line or generic failure
        "--- FAIL:",  # Go per-test marker
        "not ok ",  # Node TAP: "not ok 1 description"
    )
    if any(sig in stderr for sig in _wrong_signals_stderr):
        return FailureKind.WRONG_OUTPUT
    if any(sig in stdout for sig in _wrong_signals_stdout):
        return FailureKind.WRONG_OUTPUT

    # --- Runtime errors (uncaught exceptions, panics) ---
    _runtime_signals = (
        "Traceback",  # Python traceback
        "panic:",  # Go panic
        "ReferenceError",  # JS
        "TypeError",  # JS / Python
        "RuntimeError",  # Python
        "thread 'main' panicked",  # Rust
    )
    if any(sig in stderr for sig in _runtime_signals):
        return FailureKind.RUNTIME_ERROR

    # Non-zero exit code with no more specific classification.
    return FailureKind.RUNTIME_ERROR
