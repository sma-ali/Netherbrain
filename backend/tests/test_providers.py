import httpx
import openai
import pytest

from netherbrain.api.deps import build_registry
from netherbrain.config import Settings
from netherbrain.providers.filters import is_free_openrouter_model, is_groq_chat_model
from netherbrain.providers.openai_compatible import describe_error

REQUEST = httpx.Request("POST", "http://provider.test/v1/chat/completions")


def status_error(error_class, status: int, body: dict) -> openai.APIStatusError:
    return error_class("raw message", response=httpx.Response(status, request=REQUEST), body=body)


def make_settings(**overrides) -> Settings:
    # _env_file=None : ignore le vrai .env du développeur, pour des tests reproductibles.
    return Settings(_env_file=None, **overrides)


def test_only_ollama_is_enabled_without_api_keys():
    assert build_registry(make_settings()).names == ["ollama"]


def test_remote_providers_are_enabled_by_their_api_key():
    settings = make_settings(openrouter_api_key="sk-or-test", groq_api_key="gsk-test")

    assert build_registry(settings).names == ["ollama", "openrouter", "groq"]


def test_only_ollama_runs_locally():
    registry = build_registry(make_settings(openrouter_api_key="sk-or-test"))

    assert registry.get("ollama").local is True
    assert registry.get("openrouter").local is False


def test_an_empty_api_key_leaves_the_provider_disabled():
    assert build_registry(make_settings(groq_api_key="")).names == ["ollama"]


def test_api_keys_never_appear_in_settings_repr():
    settings = make_settings(openrouter_api_key="sk-or-test")

    assert "sk-or-test" not in repr(settings)
    assert settings.openrouter_api_key.get_secret_value() == "sk-or-test"


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("google/gemma-4-31b-it:free", True),
        ("google/gemma-4-31b-it", False),
        ("deepseek/deepseek-r1", False),
    ],
)
def test_openrouter_free_filter(model_id, expected):
    assert is_free_openrouter_model(model_id) is expected


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("llama-3.3-70b-versatile", True),
        ("qwen/qwen3-32b", True),
        ("whisper-large-v3", False),
        ("playai-tts", False),
        ("meta-llama/llama-guard-4-12b", False),
    ],
)
def test_groq_chat_filter(model_id, expected):
    assert is_groq_chat_model(model_id) is expected


def test_a_rate_limit_gets_a_short_explanation_without_account_details():
    body = {
        "error": {"message": "Provider returned error", "metadata": {"raw": "a very long text"}},
        "user_id": "user_123",
    }

    message = describe_error(status_error(openai.RateLimitError, 429, body))

    assert "rate limit" in message
    assert "user_123" not in message


def test_an_http_error_keeps_only_the_provider_message():
    body = {"error": {"message": "model 'nope' not found", "type": "not_found_error"}}

    message = describe_error(status_error(openai.NotFoundError, 404, body))

    assert message == "HTTP 404: model 'nope' not found"


def test_a_network_error_is_described_plainly():
    assert describe_error(openai.APIConnectionError(request=REQUEST)) == "Connection error."
