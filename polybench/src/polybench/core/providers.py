"""Which LLM providers PolyBench supports, and how to build one."""

from dataclasses import dataclass

from polybench.config import settings
from polybench.providers.anthropic_provider import AnthropicProvider
from polybench.providers.base import LLMProvider
from polybench.providers.mock_provider import MockProvider
from polybench.providers.openai_compatible import OpenAICompatibleProvider


@dataclass(frozen=True)
class CloudProvider:
    key_setting: str  # attribute on Settings holding the API key
    env_var: str
    probe_model: str  # cheap model `polybench compass` uses to check connectivity
    base_url: str | None = None  # OpenAI-compatible endpoint; None for Anthropic


CLOUD_PROVIDERS: dict[str, CloudProvider] = {
    "anthropic": CloudProvider(
        "anthropic_api_key", "ANTHROPIC_API_KEY", "claude-sonnet-4-6"
    ),
    "openai": CloudProvider(
        "openai_api_key", "OPENAI_API_KEY", "gpt-4o", "https://api.openai.com/v1"
    ),
    "groq": CloudProvider(
        "groq_api_key",
        "GROQ_API_KEY",
        "llama-3.3-70b-versatile",
        "https://api.groq.com/openai/v1",
    ),
    "together": CloudProvider(
        "together_api_key",
        "TOGETHER_API_KEY",
        "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "https://api.together.xyz/v1",
    ),
    "mistral": CloudProvider(
        "mistral_api_key",
        "MISTRAL_API_KEY",
        "mistral-small-latest",
        "https://api.mistral.ai/v1",
    ),
    "deepseek": CloudProvider(
        "deepseek_api_key",
        "DEEPSEEK_API_KEY",
        "deepseek-chat",
        "https://api.deepseek.com/v1",
    ),
    "xai": CloudProvider(
        "xai_api_key", "XAI_API_KEY", "grok-3-mini", "https://api.x.ai/v1"
    ),
    "gemini": CloudProvider(
        "gemini_api_key",
        "GEMINI_API_KEY",
        "gemini-2.0-flash",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
    ),
    "fireworks": CloudProvider(
        "fireworks_api_key",
        "FIREWORKS_API_KEY",
        "accounts/fireworks/models/llama-v3p3-70b-instruct",
        "https://api.fireworks.ai/inference/v1",
    ),
    "perplexity": CloudProvider(
        "perplexity_api_key",
        "PERPLEXITY_API_KEY",
        "sonar",
        "https://api.perplexity.ai",
    ),
}

# Providers that need no API key.
LOCAL_PROVIDERS = ("ollama", "lmstudio", "mock")

ALL_PROVIDERS = (*CLOUD_PROVIDERS, *LOCAL_PROVIDERS)

_LOCAL_PLACEHOLDER_KEYS = {"ollama": "ollama", "lmstudio": "lm-studio"}


class ProviderError(ValueError):
    """A provider can't be used as requested."""


class UnknownProviderError(ProviderError):
    def __init__(self, name: str) -> None:
        super().__init__(
            f"Unknown provider: {name!r}. Valid options: {', '.join(sorted(ALL_PROVIDERS))}"
        )


class MissingApiKeyError(ProviderError):
    def __init__(self, name: str, env_var: str) -> None:
        self.env_var = env_var
        super().__init__(
            f"{env_var} not set — add it to .env or set the environment variable"
        )


def api_key(name: str) -> str | None:
    """The configured API key for a cloud provider, or None."""
    spec = CLOUD_PROVIDERS.get(name)
    if spec is None:
        return None
    key: str | None = getattr(settings, spec.key_setting, None)
    return key or None


def local_base_url(name: str) -> str | None:
    """Where a local OpenAI-compatible server is expected, or None."""
    if name == "ollama":
        return settings.ollama_base_url
    if name == "lmstudio":
        return settings.lmstudio_base_url
    return None


def is_configured(name: str) -> bool:
    """Whether the provider can be used without further setup."""
    return name in LOCAL_PROVIDERS or api_key(name) is not None


def check_provider(name: str) -> None:
    """Raise UnknownProviderError or MissingApiKeyError if `name` can't be used."""
    if name in LOCAL_PROVIDERS:
        return
    spec = CLOUD_PROVIDERS.get(name)
    if spec is None:
        raise UnknownProviderError(name)
    if api_key(name) is None:
        raise MissingApiKeyError(name, spec.env_var)


def make_provider(name: str, model: str, temperature: float) -> LLMProvider:
    """Build a ready-to-use provider, or raise a ProviderError explaining why not."""
    check_provider(name)
    if name == "mock":
        return MockProvider(model=model, temperature=temperature)
    local_url = local_base_url(name)
    if local_url is not None:
        # Local servers ignore the key, but the OpenAI client requires one.
        return OpenAICompatibleProvider(
            api_key=_LOCAL_PLACEHOLDER_KEYS[name],
            base_url=local_url,
            model=model,
            temperature=temperature,
        )
    key = api_key(name)
    base_url = CLOUD_PROVIDERS[name].base_url
    if base_url is None:
        return AnthropicProvider(model=model, temperature=temperature, api_key=key)
    return OpenAICompatibleProvider(
        api_key=key or "", base_url=base_url, model=model, temperature=temperature
    )
