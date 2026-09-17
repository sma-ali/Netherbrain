"""Dépendances FastAPI, et la « composition root » qui assemble les fournisseurs.

Les routes déclarent ce dont elles ont besoin (`Depends(get_registry)`) au lieu de le
construire elles-mêmes : les tests peuvent ainsi y substituer des faux avec
`app.dependency_overrides`.
"""

from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from netherbrain.advisor.sources import ArtificialAnalysisClient
from netherbrain.agent.approvals import ApprovalRegistry
from netherbrain.config import Settings, get_settings
from netherbrain.db.models import EMBEDDING_DIMENSIONS
from netherbrain.db.session import create_engine
from netherbrain.projects.workspace import Workspace
from netherbrain.providers import (
    LLMProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    ProviderRegistry,
    UnknownProviderError,
)
from netherbrain.providers.filters import is_free_openrouter_model, is_groq_chat_model
from netherbrain.rag.embeddings import Embedder, OllamaEmbedder

# En-têtes d'attribution facultatifs : ils identifient l'application sur openrouter.ai.
OPENROUTER_HEADERS = {
    "HTTP-Referer": "https://github.com/sma-ali/Netherbrain",
    "X-Title": "Netherbrain",
}


# --- Fournisseurs de LLM ---


def build_registry(settings: Settings) -> ProviderRegistry:
    """Ollama est toujours présent ; chaque fournisseur distant s'active avec sa clé d'API."""
    providers: list[LLMProvider] = [
        OllamaProvider(settings.ollama_base_url, context_length=settings.ollama_context_length),
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


Registry = Annotated[ProviderRegistry, Depends(get_registry)]


def get_provider_or_404(registry: ProviderRegistry, name: str) -> LLMProvider:
    try:
        return registry.get(name)
    except UnknownProviderError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown provider '{name}'. Available: {', '.join(registry.names)}",
        ) from exc


# --- Base de données ---


@lru_cache
def get_engine() -> AsyncEngine:
    return create_engine(get_settings().database_url)


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False : les objets restent lisibles après commit(), pour y répondre.
    return async_sessionmaker(get_engine(), expire_on_commit=False)


SessionFactory = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]


async def get_session(factory: SessionFactory) -> AsyncIterator[AsyncSession]:
    """Une session (une « unité de travail ») par requête HTTP, fermée à la fin."""
    async with factory() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_session)]


# --- Configuration et RAG ---

SettingsDep = Annotated[Settings, Depends(get_settings)]


@lru_cache
def get_embedder() -> Embedder:
    settings = get_settings()
    return OllamaEmbedder(
        settings.ollama_base_url,
        settings.embedding_model,
        document_prefix=settings.embedding_document_prefix,
        query_prefix=settings.embedding_query_prefix,
        dimensions=EMBEDDING_DIMENSIONS,
    )


EmbedderDep = Annotated[Embedder, Depends(get_embedder)]


# --- Projets ---


@lru_cache
def get_workspace() -> Workspace:
    return Workspace(get_settings().workspace_root)


WorkspaceDep = Annotated[Workspace, Depends(get_workspace)]


@lru_cache
def get_approvals() -> ApprovalRegistry:
    """Un seul registre pour toute l'application : les demandes vivent en mémoire."""
    return ApprovalRegistry(timeout=get_settings().agent_approval_timeout)


ApprovalsDep = Annotated[ApprovalRegistry, Depends(get_approvals)]


# --- Conseiller de modèles ---


@lru_cache
def get_benchmarks_client() -> ArtificialAnalysisClient | None:
    """Le client des benchmarks en ligne, ou None sans clé d'API (grille seule)."""
    settings = get_settings()
    if key := _secret(settings.artificial_analysis_api_key):
        return ArtificialAnalysisClient(key, settings.artificial_analysis_base_url)
    return None


BenchmarksClientDep = Annotated[ArtificialAnalysisClient | None, Depends(get_benchmarks_client)]
