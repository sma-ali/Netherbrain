"""FastAPI dependencies, and the composition root that wires providers together.

Routes declare what they need (`Depends(get_registry)`) instead of building it
themselves, so tests can swap in fakes with `app.dependency_overrides`.
"""

from functools import lru_cache

from pydantic import SecretStr

from netherbrain.config import Settings, get_settings
from netherbrain.providers import LLMProvider, OpenAICompatibleProvider, ProviderRegistry
from netherbrain.providers.filters import is_free_openrouter_model, is_groq_chat_model

# Optional attribution headers: they identify the app on openrouter.ai.
OPENROUTER_HEADERS = {
    "HTTP-Referer": "https://github.com/sma-ali/Netherbrain",
    "X-Title": "Netherbrain",
}


def build_registry(settings: Settings) -> ProviderRegistry:
    """Local Ollama is always there; each remote provider is enabled by its API key."""
    providers: list[LLMProvider] = [
        OpenAICompatibleProvider("ollama", settings.ollama_base_url),
    ]
    if key := _secret(settings.openrouter_api_key):
        providers.append(
            OpenAICompatibleProvider(
                "openrouter",
                settings.openrouter_base_url,
                key,
                model_filter=is_free_openrouter_model if settings.openrouter_free_only else None,
                default_headers=OPENROUTER_HEADERS,
            )
        )
    if key := _secret(settings.groq_api_key):
        providers.append(
            OpenAICompatibleProvider(
                "groq", settings.groq_base_url, key, model_filter=is_groq_chat_model
            )
        )
    return ProviderRegistry(providers, list_timeout=settings.provider_list_timeout)


def _secret(value: SecretStr | None) -> str | None:
    """The raw key, or None when unset or left empty in .env."""
    return (value.get_secret_value() or None) if value is not None else None


@lru_cache
def get_registry() -> ProviderRegistry:
    return build_registry(get_settings())
