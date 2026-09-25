from typing import Protocol
from polybench.schemas import GenerationResult


class LLMProvider(Protocol):
    def generate(self, prompt: str) -> GenerationResult: ...
