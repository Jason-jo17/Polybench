from polybench.scoring.taxonomy import classify, FailureKind

def test_classify():
    assert classify(0, "", "", False) is None
    assert classify(None, "", "", True) == FailureKind.TIMEOUT
    assert classify(137, "", "", False) == FailureKind.MEMORY_EXCEEDED
    assert classify(1, "", "out of memory error", False) == FailureKind.MEMORY_EXCEEDED
    assert classify(1, "", "SyntaxError: invalid", False) == FailureKind.COMPILE_ERROR
    assert classify(1, "", "build failed", False) == FailureKind.COMPILE_ERROR
    assert classify(1, "FAIL", "", False) == FailureKind.WRONG_OUTPUT
    assert classify(1, "", "Traceback (most recent call last):", False) == FailureKind.RUNTIME_ERROR
    assert classify(1, "", "panic: oops", False) == FailureKind.RUNTIME_ERROR
    assert classify(1, "", "ReferenceError: x is not defined", False) == FailureKind.RUNTIME_ERROR
    assert classify(1, "", "TypeError: invalid", False) == FailureKind.RUNTIME_ERROR
    assert classify(1, "", "network is unreachable", False) == FailureKind.SECURITY_VIOLATION
    assert classify(1, "", "operation not permitted", False) == FailureKind.SECURITY_VIOLATION
    assert classify(1, "", "permission denied", False) == FailureKind.SECURITY_VIOLATION
    assert classify(42, "", "some generic error", False) == FailureKind.RUNTIME_ERROR

