"""Every provider must be able to build its HTTP client with the pinned
dependencies. anthropic 0.34 and openai 1.40 break under httpx 0.28 (they pass
a `proxies` argument it removed), which took down every real provider at once."""

from polybench.providers.anthropic_provider import AnthropicProvider
from polybench.providers.openai_compatible import OpenAICompatibleProvider


def test_anthropic_client_builds(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    AnthropicProvider(model="claude-test", temperature=0.2)


def test_openai_compatible_client_builds():
    OpenAICompatibleProvider(
        api_key="test-key",
        base_url="http://127.0.0.1:9/v1",
        model="test-model",
        temperature=0.2,
    )
