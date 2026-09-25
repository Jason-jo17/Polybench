from __future__ import annotations

import time

from polybench.providers.retry import retry_with_backoff
from polybench.schemas import GenerationResult


class OpenAICompatibleProvider:
    """LLM provider for any OpenAI-compatible API.

    Covers: OpenAI, Groq, Together AI, Mistral, DeepSeek, xAI, Google Gemini
    (v1beta/openai), Fireworks, Perplexity, Ollama, LM Studio — anything that
    accepts POST /v1/chat/completions with an OpenAI-style body.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float = 0.2,
    ) -> None:
        try:
            import openai as _openai
        except ImportError as exc:
            raise ImportError("pip install openai") from exc
        self._client = _openai.OpenAI(api_key=api_key, base_url=base_url, timeout=120.0)
        self._model = model
        self._temperature = temperature

    def generate(self, prompt: str) -> GenerationResult:
        import openai

        _SYSTEM = (
            "You are an expert software engineer. Solve the given programming task.\n"
            "Return ONLY the implementation as a single fenced code block in the target\n"
            "language. Do not include explanations, tests, usage examples, or prose.\n"
            "Match the required signature exactly."
        )

        t0 = time.monotonic()
        response = retry_with_backoff(
            lambda: self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                temperature=self._temperature,
            ),
            retryable=(openai.RateLimitError, openai.APIConnectionError),
        )
        runtime_ms = int((time.monotonic() - t0) * 1000)
        text = (response.choices[0].message.content or "") if response.choices else ""
        usage = response.usage
        return GenerationResult(
            raw_output=text,
            runtime_ms=runtime_ms,
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
        )
