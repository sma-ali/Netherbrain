from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration de l'application, lue depuis les variables d'environnement (ou un .env)."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="NETHERBRAIN_", extra="ignore")

    # Base PostgreSQL. Par défaut, celle du service « db » de Compose, publiée sur localhost.
    database_url: str = "postgresql+asyncpg://netherbrain:netherbrain@localhost:5432/netherbrain"

    # Fournisseur local : toujours activé.
    ollama_base_url: str = "http://localhost:11434/v1"

    # Fournisseurs distants : activés seulement si leur clé d'API est renseignée.
    # SecretStr garde les clés hors des logs, des tracebacks et de repr().
    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_free_only: bool = True
    groq_api_key: SecretStr | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # Délai max accordé à chaque fournisseur par /api/models avant de le déclarer indisponible.
    provider_list_timeout: float = 5.0

    # --- RAG : discuter avec ses documents ---
    # Modèle d'embeddings servi par Ollama. Il doit produire des vecteurs de 768 dimensions,
    # la taille de la colonne en base.
    embedding_model: str = "nomic-embed-text"
    # nomic-embed-text attend un préfixe qui indique le rôle du texte : document ou question.
    embedding_document_prefix: str = "search_document: "
    embedding_query_prefix: str = "search_query: "
    # Nombre d'extraits ajoutés au prompt, et découpage des documents (en caractères).
    rag_top_k: int = 5
    chunk_size: int = 1200
    chunk_overlap: int = 200
    max_upload_mb: int = 20

    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
