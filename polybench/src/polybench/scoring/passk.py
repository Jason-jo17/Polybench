import math


def pass_at_k(n: int, c: int, k: int) -> float:
    """Calculates the unbiased pass@k estimator."""
    if k > n or n < 0 or c < 0 or k < 0:
        raise ValueError(f"Invalid parameters for pass@k: n={n}, c={c}, k={k}")

    if (n - c) >= k:
        return 1.0 - (math.comb(n - c, k) / math.comb(n, k))
    return 1.0
