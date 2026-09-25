"""Shared exponential-backoff retry helper for LLM provider calls."""
from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    retryable: tuple[type[Exception], ...],
    max_retries: int = 5,
    base_delay: float = 2.0,
) -> T:
    """Call fn(), retrying on retryable exceptions with exponential backoff + jitter.

    Delay formula: base_delay * 2^attempt + U(0, 1)
    This prevents thundering-herd when many workers hit the same rate limit.

    Raises the last exception if all retries are exhausted.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            return fn()
        except retryable as exc:
            last_exc = exc
            if attempt == max_retries - 1:
                break
            delay = base_delay * (2**attempt) + random.uniform(0.0, 1.0)
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc
