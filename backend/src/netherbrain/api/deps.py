"""FastAPI dependencies: how routes get the objects they need.

Routes declare what they need (`Depends(get_provider)`) instead of building it
themselves, so tests can swap in a fake with `app.dependency_overrides`.
"""

from functools import lru_cache

from netherbrain.config import get_settings
from netherbrain.providers import LLMProvider, OpenAICompatibleProvider


@lru_cache
def get_provider() -> LLMProvider:
    settings = get_settings()
    return OpenAICompatibleProvider(name="ollama", base_url=settings.ollama_base_url)
