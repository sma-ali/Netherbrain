import asyncio
import json
import os
import re
import zlib
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool, StaticPool

from netherbrain.api.deps import get_embedder, get_registry, get_session_factory, get_workspace
from netherbrain.db.models import EMBEDDING_DIMENSIONS, Base
from netherbrain.db.session import enable_pgvector
from netherbrain.main import app
from netherbrain.projects.workspace import Workspace
from netherbrain.providers import ProviderError, ProviderRegistry
from netherbrain.rag.embeddings import EmbeddingError
from netherbrain.schemas import ChatMessage, ModelCard, StreamEvent

# Par défaut, les tests tournent sur SQLite en mémoire : rapide, rien à installer.
# La CI les relance sur un vrai PostgreSQL (avec pgvector) en définissant cette variable.
TEST_DATABASE_URL = os.environ.get("NETHERBRAIN_TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")


class FakeProvider:
    """Remplace un vrai LLM : rejoue des événements écrits à l'avance, sans réseau ni GPU."""

    def __init__(
        self,
        name: str = "fake",
        models: list[str] | None = None,
        events: list[StreamEvent] | None = None,
        fail: bool = False,
        list_delay: float = 0.0,
        local: bool = False,
    ) -> None:
        self.name = name
        self.local = local
        self.models = models if models is not None else [f"{name}-model"]
        self.events = events or []
        self.fail = fail
        self.list_delay = list_delay
        self.received: list[ChatMessage] = []

    async def list_models(self) -> list[str]:
        if self.list_delay:
            await asyncio.sleep(self.list_delay)
        if self.fail:
            raise ProviderError(f"{self.name}: unreachable")
        return self.models

    async def describe_models(self) -> list[ModelCard]:
        return [
            ModelCard(id=model_id, provider=self.name, local=self.local, name=model_id)
            for model_id in await self.list_models()
        ]

    async def stream_chat(
        self, model: str, messages: list[ChatMessage]
    ) -> AsyncIterator[StreamEvent]:
        self.received = messages
        for scripted in self.events:
            yield scripted
        if self.fail:
            raise ProviderError(f"{self.name}: connection lost")


class FakeEmbedder:
    """Des vecteurs calculés sans modèle, en « sac de mots » : chaque mot allume une case.

    Deux textes qui partagent des mots ont donc des vecteurs proches : suffisant pour
    vérifier que la recherche remonte le bon document, sans GPU ni réseau.
    """

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def _vector(self, content: str) -> list[float]:
        if self.fail:
            raise EmbeddingError("fake embedding model unreachable")
        vector = [0.0] * EMBEDDING_DIMENSIONS
        for word in re.findall(r"\w+", content.lower()):
            vector[zlib.crc32(word.encode()) % EMBEDDING_DIMENSIONS] += 1.0
        return vector


def make_test_engine(url: str) -> AsyncEngine:
    if not url.startswith("sqlite"):
        # NullPool : aucune connexion gardée entre deux tests (chacun a sa boucle d'événements).
        engine = create_async_engine(url, poolclass=NullPool)
        enable_pgvector(engine)
        return engine

    # StaticPool : une seule connexion partagée. Sinon chaque connexion ouvrirait
    # sa propre base en mémoire… vide.
    engine = create_async_engine(
        url, poolclass=StaticPool, connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(dbapi_connection, _record) -> None:
        # SQLite n'applique les clés étrangères (et ON DELETE CASCADE) que sur demande.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


async def create_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await connection.run_sync(Base.metadata.create_all)


async def drop_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Un client HTTP de test, branché sur une base neuve pour chaque test."""
    engine = make_test_engine(TEST_DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    app.dependency_overrides[get_session_factory] = lambda: factory

    # Le « with » démarre la boucle d'événements de l'application : la base est créée dedans.
    with TestClient(app) as test_client:
        test_client.portal.call(create_schema, engine)
        test_client.session_factory = factory  # pour inspecter la base depuis un test
        yield test_client
        test_client.portal.call(drop_schema, engine)
    app.dependency_overrides.clear()


@pytest.fixture
def use_providers():
    """Remplace les vrais fournisseurs par des faux pendant le test en cours."""

    def install(*providers: FakeProvider, list_timeout: float = 1.0) -> ProviderRegistry:
        registry = ProviderRegistry(list(providers), list_timeout=list_timeout)
        app.dependency_overrides[get_registry] = lambda: registry
        return registry

    return install


@pytest.fixture
def use_embedder():
    """Remplace le modèle d'embeddings (Ollama) par un faux pendant le test en cours."""

    def install(embedder: FakeEmbedder) -> FakeEmbedder:
        app.dependency_overrides[get_embedder] = lambda: embedder
        return embedder

    return install


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Un dossier de travail jetable, à la place de ~/Projects, pendant le test en cours."""
    root = tmp_path / "workspace"
    root.mkdir()
    app.dependency_overrides[get_workspace] = lambda: Workspace(root)
    return root


def parse_sse(body: str) -> list[tuple[str, dict]]:
    """Transforme un corps SSE brut en liste de paires (événement, données)."""
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events
