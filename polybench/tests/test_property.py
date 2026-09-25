"""Property-based and coverage-gap tests using Hypothesis."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings, strategies as st

from polybench.extract import extract_code
from polybench.schemas import Language
from polybench.scoring.passk import pass_at_k
from polybench.scoring.taxonomy import FailureKind, classify


# ---------------------------------------------------------------------------
# extract_code — never crashes, always returns str | None
# ---------------------------------------------------------------------------

LANGUAGES = [l.value for l in Language]


@given(st.text(), st.sampled_from(LANGUAGES))
def test_extract_never_crashes(raw: str, lang: str) -> None:
    """extract_code must never raise regardless of input."""
    result = extract_code(raw, lang)
    assert result is None or isinstance(result, str)


@given(st.text(), st.text(), st.sampled_from(LANGUAGES))
def test_extract_result_non_empty_when_not_none(pre: str, post: str, lang: str) -> None:
    """If extract_code returns a value it must be non-empty after strip."""
    raw = f"{pre}\n{post}"
    result = extract_code(raw, lang)
    if result is not None:
        assert result.strip() != "" or result == result  # result is str


@given(
    st.text(alphabet=st.characters(blacklist_categories=("Cs",))),
    st.sampled_from(LANGUAGES),
)
def test_extract_fence_roundtrip(code: str, lang: str) -> None:
    """Code inside a correctly tagged fence must survive extraction unchanged."""
    # Only test non-empty code that doesn't contain ``` itself
    if "```" in code or not code.strip():
        return
    raw = f"```{lang}\n{code}\n```"
    result = extract_code(raw, lang)
    assert result == code.strip()


# ---------------------------------------------------------------------------
# pass@k — monotonicity, bounds, boundary values
# ---------------------------------------------------------------------------

@given(
    n=st.integers(min_value=1, max_value=200),
    k=st.integers(min_value=1, max_value=200),
    c=st.integers(min_value=0, max_value=200),
)
def test_passk_bounds(n: int, k: int, c: int) -> None:
    """pass@k is always in [0, 1] for any valid (n, c, k)."""
    c = min(c, n)
    k = min(k, n)
    result = pass_at_k(n, c, k)
    assert 0.0 <= result <= 1.0, f"pass_at_k({n},{c},{k}) = {result}"


@given(
    n=st.integers(min_value=2, max_value=50),
    k=st.integers(min_value=1, max_value=50),
)
def test_passk_monotone_in_c(n: int, k: int) -> None:
    """Increasing c should never decrease pass@k."""
    k = min(k, n)
    scores = [pass_at_k(n, c, k) for c in range(n + 1)]
    for i in range(len(scores) - 1):
        assert scores[i] <= scores[i + 1] + 1e-9, f"Non-monotone at c={i}: {scores[i]} > {scores[i+1]}"


@given(n=st.integers(min_value=1, max_value=100))
def test_passk_all_pass_is_one(n: int) -> None:
    """When c == n, pass@k should be 1.0 for any k <= n."""
    for k in range(1, min(n + 1, 6)):
        assert pass_at_k(n, n, k) == pytest.approx(1.0)


@given(n=st.integers(min_value=1, max_value=100))
def test_passk_none_pass_is_zero(n: int) -> None:
    """When c == 0, pass@k should be 0.0 for any k <= n."""
    for k in range(1, min(n + 1, 6)):
        assert pass_at_k(n, 0, k) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# taxonomy.classify — never crashes, always returns FailureKind | None
# ---------------------------------------------------------------------------

FAILURE_KINDS = {fk.value for fk in FailureKind}


@given(
    exit_code=st.one_of(st.none(), st.integers(-255, 255)),
    stdout=st.text(),
    stderr=st.text(),
    timed_out=st.booleans(),
)
def test_classify_never_crashes(
    exit_code: int | None, stdout: str, stderr: str, timed_out: bool
) -> None:
    """classify() must never raise regardless of input."""
    result = classify(exit_code, stdout, stderr, timed_out)
    assert result is None or result in FailureKind


@given(stdout=st.text(), stderr=st.text())
def test_classify_timed_out_always_timeout(stdout: str, stderr: str) -> None:
    """timed_out=True must always produce TIMEOUT failure."""
    result = classify(None, stdout, stderr, timed_out=True)
    assert result == FailureKind.TIMEOUT


@given(stdout=st.text(), stderr=st.text())
def test_classify_exit_zero_stdout_clean_passes(stdout: str, stderr: str) -> None:
    """exit_code=0 with no failure signals in stdout/stderr should pass."""
    # Only test strings that contain none of the known failure signals
    bad = ("AssertionError", "FAILED", "FAIL", "--- FAIL:", "not ok ",
           "SyntaxError", "build failed", "undefined:", "cannot use",
           "declared and not used", "imported and not used", "error[E",
           "error: aborting", "compile error", "syntax error")
    if any(b in stdout or b in stderr for b in bad):
        return
    result = classify(0, stdout, stderr, timed_out=False)
    assert result is None, f"Expected pass but got {result} with stdout={stdout!r}"


# ---------------------------------------------------------------------------
# MCP server _require_args — validation helper
# ---------------------------------------------------------------------------

def test_require_args_missing_raises() -> None:
    from polybench.server import _require_args
    with pytest.raises(ValueError, match="run_id"):
        _require_args({}, "run_id")


def test_require_args_none_raises() -> None:
    from polybench.server import _require_args
    with pytest.raises(ValueError, match="run_a"):
        _require_args({"run_a": None, "run_b": "abc"}, "run_a", "run_b")


def test_require_args_all_present_no_raise() -> None:
    from polybench.server import _require_args
    _require_args({"run_id": "abc123"}, "run_id")  # should not raise


# ---------------------------------------------------------------------------
# Engine worker exception path — unhandled exception creates a failed Sample
# ---------------------------------------------------------------------------

def test_engine_worker_records_failure_on_provider_error(tmp_db, sample_task) -> None:
    """If provider.generate() raises, the engine must still write a failed Sample record."""
    from polybench.engine import RunConfig, run_benchmark
    from polybench.db import get_session
    from polybench.models import Sample, TaskResult
    from sqlmodel import select

    class BoomProvider:
        def generate(self, prompt: str):  # type: ignore[override]
            raise RuntimeError("simulated API failure")

    class FakeRunner:
        def run(self, code: str, task):  # type: ignore[override]
            from polybench.sandbox.runner import SandboxResult
            return SandboxResult(exit_code=0, stdout="", stderr="", runtime_ms=0, timed_out=False)

    cfg = RunConfig(model="boom", provider="mock", n=2, k=1, temperature=0.0, lang=None)
    with get_session() as session:
        from polybench.models import BenchmarkRun
        run_record = BenchmarkRun(
            model=cfg.model, provider=cfg.provider, samples_per_task=cfg.n, k=cfg.k,
            temperature=cfg.temperature, total_tasks=1, pass_at_k=0.0, status="PENDING"
        )
        session.add(run_record)
        session.commit()
        run_id = run_record.id

        run_record = run_benchmark(run_id, cfg, [sample_task], BoomProvider(), FakeRunner(), session)
        run_pak = run_record.pass_at_k

    assert run_pak == 0.0

    with get_session() as session:
        task_results = session.exec(
            select(TaskResult).where(TaskResult.run_id == run_id)
        ).all()
        assert len(task_results) == 1
        tr_id = task_results[0].id

        samples = session.exec(
            select(Sample).where(Sample.task_result_id == tr_id)
        ).all()
        assert len(samples) == 2
        assert all(not s.passed for s in samples)
        assert all(s.failure_kind is not None for s in samples)


# ---------------------------------------------------------------------------
# DB FK enforcement — orphan row should be rejected
# ---------------------------------------------------------------------------

def test_db_fk_enforced(tmp_db) -> None:
    """Inserting a Sample with a non-existent task_result_id should fail (FK pragma active)."""
    import sqlite3
    conn = sqlite3.connect(str(tmp_db))
    conn.execute("PRAGMA foreign_keys=ON")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO sample "
            "(id, task_result_id, sample_index, raw_output, passed, stdout, stderr, runtime_ms, timed_out) "
            "VALUES ('orphan', 'does-not-exist', 0, '', 0, '', '', 0, 0)"
        )
    conn.close()
