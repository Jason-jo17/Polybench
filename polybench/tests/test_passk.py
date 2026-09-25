import pytest
from hypothesis import given, strategies as st
from polybench.scoring.passk import pass_at_k


@given(st.integers(min_value=1, max_value=100), st.integers(min_value=1, max_value=100))
def test_pass_at_k_properties(n, k):
    if k > n:
        return
    for c in range(n + 1):
        pk = pass_at_k(n, c, k)
        assert 0.0 <= pk <= 1.0
        if c == n:
            assert pk == 1.0
        if c > 0:
            pk_prev = pass_at_k(n, c - 1, k)
            assert pk >= pk_prev


def test_pass_at_k_invalid():
    with pytest.raises(ValueError):
        pass_at_k(-1, 0, 1)
