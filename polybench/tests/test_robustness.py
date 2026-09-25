import anthropic
import openai
import pytest
from unittest.mock import MagicMock

from polybench.providers.anthropic_provider import AnthropicProvider
from polybench.providers.openai_compatible import OpenAICompatibleProvider


def test_setup_command(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = [
        MagicMock(returncode=0),  # docker info
        MagicMock(returncode=0),  # inspect python
        MagicMock(returncode=0),  # inspect node
        MagicMock(returncode=0),  # inspect go
        MagicMock(returncode=0),  # inspect rust
    ]
    from typer.testing import CliRunner
    from polybench.cli import app

    runner = CliRunner()
    res = runner.invoke(app, ["setup"])
    assert res.exit_code == 0
    assert "setup complete" in res.stdout.lower()


def test_anthropic_retries(mocker):
    mock_client = MagicMock()
    mocker.patch("anthropic.Anthropic", return_value=mock_client)

    provider = AnthropicProvider(model="claude-test")
    mock_create = mock_client.messages.create

    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_err = anthropic.RateLimitError(
        "Rate limit exceeded", response=mock_response, body=None
    )

    mock_success = MagicMock()
    mock_block = MagicMock(spec=anthropic.types.TextBlock)
    mock_block.text = "def test(): pass"
    mock_block.type = "text"
    mock_success.content = [mock_block]
    mock_success.usage.input_tokens = 10
    mock_success.usage.output_tokens = 5

    mock_create.side_effect = [mock_err, mock_success]
    mocker.patch("time.sleep")

    res = provider.generate("test prompt")
    assert res.raw_output == "def test(): pass"
    assert mock_create.call_count == 2


def test_anthropic_retries_exhausted(mocker):
    """All retries fail — should re-raise the last exception."""
    mock_client = MagicMock()
    mocker.patch("anthropic.Anthropic", return_value=mock_client)

    provider = AnthropicProvider(model="claude-test")
    mock_response = MagicMock()
    mock_response.status_code = 429
    err = anthropic.RateLimitError("always fails", response=mock_response, body=None)
    mock_client.messages.create.side_effect = err
    mocker.patch("time.sleep")

    with pytest.raises(anthropic.RateLimitError):
        provider.generate("prompt")


def test_openai_compatible_retries(mocker):
    """OpenAICompatibleProvider (the live code path for openai/groq/etc.) retries on RateLimitError."""
    mock_client = MagicMock()
    mocker.patch("openai.OpenAI", return_value=mock_client)

    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        model="gpt-test",
    )
    mock_create = mock_client.chat.completions.create

    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_err = openai.RateLimitError(
        "Rate limit exceeded", response=mock_response, body=None
    )

    mock_success = MagicMock()
    mock_message = MagicMock()
    mock_message.content = "def test_compat(): pass"
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_success.choices = [mock_choice]
    mock_success.usage.prompt_tokens = 8
    mock_success.usage.completion_tokens = 4

    mock_create.side_effect = [mock_err, mock_success]
    mocker.patch("time.sleep")

    res = provider.generate("test prompt")
    assert res.raw_output == "def test_compat(): pass"
    assert mock_create.call_count == 2
    assert res.input_tokens == 8
    assert res.output_tokens == 4


def test_openai_compatible_retries_exhausted(mocker):
    """All retries fail for OpenAICompatibleProvider."""
    mock_client = MagicMock()
    mocker.patch("openai.OpenAI", return_value=mock_client)

    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://api.groq.com/openai/v1",
        model="llama-3.3-70b-versatile",
    )
    mock_response = MagicMock()
    mock_response.status_code = 429
    err = openai.RateLimitError("always fails", response=mock_response, body=None)
    mock_client.chat.completions.create.side_effect = err
    mocker.patch("time.sleep")

    with pytest.raises(openai.RateLimitError):
        provider.generate("prompt")


def test_retry_jitter_applied(mocker):
    """Retry sleeps include jitter (sleep amount should vary across calls)."""
    import random

    mock_client = MagicMock()
    mocker.patch("openai.OpenAI", return_value=mock_client)

    provider = OpenAICompatibleProvider(api_key="k", base_url="http://x/v1", model="m")
    mock_response = MagicMock()
    mock_response.status_code = 429
    err = openai.RateLimitError("rl", response=mock_response, body=None)

    # 2 failures then success
    mock_success = MagicMock()
    mock_success.choices = [MagicMock()]
    mock_success.choices[0].message.content = "ok"
    mock_success.usage.prompt_tokens = 1
    mock_success.usage.completion_tokens = 1
    mock_client.chat.completions.create.side_effect = [err, err, mock_success]

    sleep_calls: list[float] = []
    mocker.patch("time.sleep", side_effect=lambda d: sleep_calls.append(d))
    # Seed random so jitter is deterministic but non-zero
    random.seed(42)

    provider.generate("x")
    assert len(sleep_calls) == 2
    # With jitter, sleep amounts should not be exact powers of 2
    assert sleep_calls[0] != 2.0
    assert sleep_calls[1] != 4.0
