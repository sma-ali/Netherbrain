import pytest

from netherbrain.api.deps import build_registry
from netherbrain.config import Settings
from netherbrain.providers.filters import is_free_openrouter_model, is_groq_chat_model


def make_settings(**overrides) -> Settings:
    # _env_file=None : ignore le vrai .env du développeur, pour des tests reproductibles.
    return Settings(_env_file=None, **overrides)


def test_only_ollama_is_enabled_without_api_keys():
    assert build_registry(make_settings()).names == ["ollama"]


def test_remote_providers_are_enabled_by_their_api_key():
    settings = make_settings(openrouter_api_key="sk-or-test", groq_api_key="gsk-test")

    assert build_registry(settings).names == ["ollama", "openrouter", "groq"]


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
