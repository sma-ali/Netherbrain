from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from environment variables (or a .env file)."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="NETHERBRAIN_", extra="ignore")

    # Local provider: always enabled.
    ollama_base_url: str = "http://localhost:11434/v1"

    # Remote providers: enabled only when their API key is set.
    # SecretStr keeps keys out of logs, tracebacks and repr().
    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_free_only: bool = True
    groq_api_key: SecretStr | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # How long /api/models waits for each provider before marking it unavailable.
    provider_list_timeout: float = 5.0

    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
