import pytest

from polybench.scoring.taxonomy import classify, FailureKind


def test_classify():
    assert classify(0, "", "", False) is None
    assert classify(None, "", "", True) == FailureKind.TIMEOUT
    assert classify(137, "", "", False) == FailureKind.MEMORY_EXCEEDED
    assert classify(1, "", "out of memory error", False) == FailureKind.MEMORY_EXCEEDED
    assert classify(1, "", "SyntaxError: invalid", False) == FailureKind.COMPILE_ERROR
    assert classify(1, "", "build failed", False) == FailureKind.COMPILE_ERROR
    assert classify(1, "FAIL", "", False) == FailureKind.WRONG_OUTPUT
    assert (
        classify(1, "", "Traceback (most recent call last):", False)
        == FailureKind.RUNTIME_ERROR
    )
    assert classify(1, "", "panic: oops", False) == FailureKind.RUNTIME_ERROR
    assert (
        classify(1, "", "ReferenceError: x is not defined", False)
        == FailureKind.RUNTIME_ERROR
    )
    assert classify(1, "", "TypeError: invalid", False) == FailureKind.RUNTIME_ERROR
    assert (
        classify(1, "", "network is unreachable", False)
        == FailureKind.SECURITY_VIOLATION
    )
    assert (
        classify(1, "", "operation not permitted", False)
        == FailureKind.SECURITY_VIOLATION
    )
    assert classify(1, "", "permission denied", False) == FailureKind.SECURITY_VIOLATION
    assert classify(42, "", "some generic error", False) == FailureKind.RUNTIME_ERROR


@pytest.mark.parametrize(
    "stdout",
    [
        "# SyntaxError: Named export 'deepClone' not found.",  # Node TAP output
        "FAIL\tsolution [build failed]",  # go test
        "ERROR collecting test_solution.py\nImportError: cannot import name 'two_sum'",
        "error[E0425]: cannot find value `x` in this scope",  # rustc via stdout
    ],
)
def test_compile_errors_reported_on_stdout(stdout):
    assert classify(1, stdout, "", False) == FailureKind.COMPILE_ERROR


def test_ordinary_test_failure_on_stdout_is_still_wrong_output():
    stdout = "FAILED test_solution.py::test_basic - AssertionError: assert 2 == 3"
    assert classify(1, stdout, "", False) == FailureKind.WRONG_OUTPUT


def test_go_test_binary_compile_failure_is_a_compile_error():
    stderr = (
        "# solution [solution.test]\n"
        "./solution_test.go:7:8: s.IsEmpty undefined "
        "(type *Stack has no field or method IsEmpty)\n"
    )
    assert classify(1, "", stderr, False) == FailureKind.COMPILE_ERROR


def test_go_test_failure_is_wrong_output():
    stdout = "--- FAIL: TestStackBasic (0.00s)\n    solution_test.go:7: bad\nFAIL\n"
    assert classify(1, stdout, "", False) == FailureKind.WRONG_OUTPUT
