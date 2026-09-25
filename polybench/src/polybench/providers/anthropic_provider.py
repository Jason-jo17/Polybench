import time

import anthropic

from polybench.providers.base import LLMProvider
from polybench.providers.retry import retry_with_backoff
from polybench.schemas import GenerationResult

_SYSTEM = (
    "You are an expert software engineer. Solve the given programming task.\n"
    "Return ONLY the implementation as a single fenced code block in the target\n"
    "language. Do not include explanations, tests, usage examples, or prose.\n"
    "Match the required signature exactly."
)


class AnthropicProvider(LLMProvider):
    _API_TIMEOUT = 120.0  # seconds before treating call as hung

    def __init__(self, model: str, temperature: float = 0.2) -> None:
        self.model = model
        self.temperature = temperature
        self.client = anthropic.Anthropic(timeout=self._API_TIMEOUT)

    def generate(self, prompt: str) -> GenerationResult:
        start = time.perf_counter()

        response = retry_with_backoff(
            lambda: self.client.messages.create(
                model=self.model,
                max_tokens=8192,
                temperature=self.temperature,
                system=_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            ),
            retryable=(anthropic.RateLimitError, anthropic.APIConnectionError),
        )

        runtime_ms = int((time.perf_counter() - start) * 1000)
        text = "".join(
            block.text
            for block in response.content
            if isinstance(block, anthropic.types.TextBlock)
        )
        return GenerationResult(
            raw_output=text,
            runtime_ms=runtime_ms,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
