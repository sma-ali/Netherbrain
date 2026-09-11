"""Dépendances FastAPI, et la « composition root » qui assemble les fournisseurs.

Les routes déclarent ce dont elles ont besoin (`Depends(get_registry)`) au lieu de le
construire elles-mêmes : les tests peuvent ainsi y substituer des faux avec
`app.dependency_overrides`.
"""

from functools import lru_cache

from pydantic import SecretStr

from netherbrain.config import Settings, get_settings
from netherbrain.providers import LLMProvider, OpenAICompatibleProvider, ProviderRegistry
from netherbrain.providers.filters import is_free_openrouter_model, is_groq_chat_model

# En-têtes d'attribution facultatifs : ils identifient l'application sur openrouter.ai.
OPENROUTER_HEADERS = {
    "HTTP-Referer": "https://github.com/sma-ali/Netherbrain",
    "X-Title": "Netherbrain",
}


def build_registry(settings: Settings) -> ProviderRegistry:
    """Ollama est toujours présent ; chaque fournisseur distant s'active avec sa clé d'API."""
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
    """La clé brute, ou None si elle est absente ou laissée vide dans le .env."""
    return (value.get_secret_value() or None) if value is not None else None


@lru_cache
def get_registry() -> ProviderRegistry:
    return build_registry(get_settings())
