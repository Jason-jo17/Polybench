"""Deterministic, network-free provider for demos and tests.

It answers from each task's reference solution, so a mock run exercises the
whole pipeline (extraction, sandbox, scoring) in every language without an API
key. The model name chooses how often it answers correctly:

- ``perfect``: always the reference solution
- ``broken``: always the bare signature, which the hidden tests reject
- ``demo``: correct about 70% of the time; ``demo-40`` about 40%, and so on

Which samples pass is decided by hashing the prompt and the sample number, so
the same run always produces the same results. Prompts that don't belong to a
known task (as in unit tests) get a trivial fallback answer.
"""

import hashlib
import re
import threading
from functools import lru_cache

from polybench.config import PROJECT_ROOT
from polybench.providers.base import LLMProvider
from polybench.schemas import GenerationResult, Task

_FALLBACK_PASS = "```python\ndef solution(): return 42\n```"
_FALLBACK_FAIL = "```python\ndef solution(): raise ValueError('mock fail')\n```"
_DEFAULT_PASS_RATE = 70


@lru_cache(maxsize=1)
def _known_tasks() -> tuple[Task, ...]:
    from polybench.tasks.loader import load_tasks

    try:
        return tuple(load_tasks(PROJECT_ROOT / "tasks"))
    except Exception:
        return ()


def _task_for(prompt: str) -> Task | None:
    """The task whose signature appears in the prompt the engine built."""
    matches = [t for t in _known_tasks() if t.signature and t.signature in prompt]
    return max(matches, key=lambda t: len(t.signature), default=None)


def _pass_rate(model: str) -> int:
    if model == "perfect":
        return 100
    if model == "broken":
        return 0
    m = re.fullmatch(r"demo-(\d{1,3})", model)
    if m:
        return min(100, int(m.group(1)))
    return _DEFAULT_PASS_RATE if model == "demo" else 100


class MockProvider(LLMProvider):
    def __init__(self, model: str = "demo", temperature: float = 0.2) -> None:
        self.model = model
        self.temperature = temperature
        self.should_pass = True
        self._pass_rate = _pass_rate(model)
        self._calls: dict[str, int] = {}
        self._lock = threading.Lock()

    def _passes(self, prompt: str) -> bool:
        if not self.should_pass:
            return False
        with self._lock:
            n = self._calls.get(prompt, 0)
            self._calls[prompt] = n + 1
        digest = hashlib.sha256(f"{self.model}\n{n}\n{prompt}".encode()).digest()
        return digest[0] * 100 // 256 < self._pass_rate

    def generate(self, prompt: str) -> GenerationResult:
        passes = self._passes(prompt)
        task = _task_for(prompt)
        if task is None or not task.reference_solution:
            text = _FALLBACK_PASS if passes else _FALLBACK_FAIL
        else:
            code = task.reference_solution if passes else task.signature
            text = f"```{task.language}\n{code}\n```"
        return GenerationResult(raw_output=text, runtime_ms=1)
