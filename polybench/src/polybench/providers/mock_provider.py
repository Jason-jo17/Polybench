"""Deterministic, network-free provider used exclusively in tests."""

from polybench.providers.base import LLMProvider
from polybench.schemas import GenerationResult

# Keyed by substring of task prompt; value is (passing_code, failing_code).
_CANNED: dict[str, tuple[str, str]] = {
    "compare_versions": (
        "```python\ndef compare_versions(a: str, b: str) -> int:\n"
        "    pa, pb = [int(x) for x in a.split('.')], [int(x) for x in b.split('.')]\n"
        "    length = max(len(pa), len(pb))\n"
        "    pa += [0] * (length - len(pa)); pb += [0] * (length - len(pb))\n"
        "    for x, y in zip(pa, pb):\n"
        "        if x < y: return -1\n"
        "        if x > y: return 1\n"
        "    return 0\n```",
        "```python\ndef compare_versions(a: str, b: str) -> int:\n    raise ValueError('not implemented')\n```",
    ),
    "LRUCache": (
        "```python\nfrom collections import OrderedDict\n"
        "class LRUCache:\n"
        "    def __init__(self, capacity: int) -> None:\n"
        "        self.cap = capacity; self.cache: OrderedDict[int, int] = OrderedDict()\n"
        "    def get(self, key: int) -> int:\n"
        "        if key not in self.cache: return -1\n"
        "        self.cache.move_to_end(key); return self.cache[key]\n"
        "    def put(self, key: int, value: int) -> None:\n"
        "        if key in self.cache: self.cache.move_to_end(key)\n"
        "        self.cache[key] = value\n"
        "        if len(self.cache) > self.cap: self.cache.popitem(last=False)\n```",
        "```python\nclass LRUCache:\n"
        "    def __init__(self, capacity: int) -> None: pass\n"
        "    def get(self, key: int) -> int: return -1\n"
        "    def put(self, key: int, value: int) -> None: pass\n```",
    ),
    "SafeCounter": (
        '```go\npackage solution\nimport "sync"\n'
        "type SafeCounter struct{ mu sync.Mutex; n int }\n"
        "func (c *SafeCounter) Inc() { c.mu.Lock(); c.n++; c.mu.Unlock() }\n"
        "func (c *SafeCounter) Value() int { c.mu.Lock(); defer c.mu.Unlock(); return c.n }\n```",
        "```go\npackage solution\ntype SafeCounter struct{ n int }\n"
        "func (c *SafeCounter) Inc() { c.n++ }\n"
        "func (c *SafeCounter) Value() int { return c.n }\n```",
    ),
    "debounce": (
        "```javascript\nexport function debounce(fn, waitMs) {\n"
        "  let t; return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), waitMs); };\n}\n```",
        "```javascript\nexport function debounce(fn, waitMs) { return fn; }\n```",
    ),
}

_DEFAULT_PASS = "```python\ndef solution(): return 42\n```"
_DEFAULT_FAIL = "```python\ndef solution(): raise ValueError('mock fail')\n```"


class MockProvider(LLMProvider):
    def __init__(self, model: str = "mock", temperature: float = 0.2) -> None:
        self.model = model
        self.temperature = temperature
        self.should_pass = True

    def generate(self, prompt: str) -> GenerationResult:
        for key, (passing, failing) in _CANNED.items():
            if key in prompt:
                text = passing if self.should_pass else failing
                return GenerationResult(raw_output=text, runtime_ms=1)
        text = _DEFAULT_PASS if self.should_pass else _DEFAULT_FAIL
        return GenerationResult(raw_output=text, runtime_ms=1)
