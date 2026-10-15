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

from netherbrain.agent.approvals import ApprovalRegistry
from netherbrain.api.deps import (
    get_approvals,
    get_benchmarks_client,
    get_embedder,
    get_reach,
    get_registry,
    get_session_factory,
    get_workspace,
)
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
        turns: list[list[StreamEvent]] | None = None,
        fail: bool = False,
        list_delay: float = 0.0,
        local: bool = False,
        capabilities: list[str] | None = None,
        json_reply: dict | None = None,
    ) -> None:
        self.name = name
        self.local = local
        self.models = models if models is not None else [f"{name}-model"]
        self.events = events or []
        # Un scénario par tour de boucle de l'agent ; sinon `events` est rejoué à chaque tour.
        self.turns = list(turns) if turns is not None else None
        self.fail = fail
        self.list_delay = list_delay
        self.capabilities = capabilities or []
        self.received: list[ChatMessage] = []
        # Les historiques envoyés au modèle, un par appel (utile en mode agent).
        self.histories: list[list[ChatMessage]] = []
        self.tools: list[dict] | None = None
        # La réponse aux demandes de sortie structurée ; None : le fournisseur échoue.
        self.json_reply = json_reply
        self.json_requests: list[tuple[str, list[ChatMessage], dict, bool | None]] = []

    async def list_models(self) -> list[str]:
        if self.list_delay:
            await asyncio.sleep(self.list_delay)
        if self.fail:
            raise ProviderError(f"{self.name}: unreachable")
        return self.models

    async def describe_models(self) -> list[ModelCard]:
        return [
            ModelCard(
                id=model_id,
                provider=self.name,
                local=self.local,
                name=model_id,
                capabilities=list(self.capabilities),
            )
            for model_id in await self.list_models()
        ]

    async def stream_chat(
        self, model: str, messages: list[ChatMessage], tools: list[dict] | None = None
    ) -> AsyncIterator[StreamEvent]:
        self.received = messages
        self.histories.append(list(messages))
        self.tools = tools
        scenario = self.events if self.turns is None else (self.turns.pop(0) if self.turns else [])
        for scripted in scenario:
            yield scripted
        if self.fail:
            raise ProviderError(f"{self.name}: connection lost")

    async def complete_json(
        self, model: str, messages: list[ChatMessage], schema: dict, *, think: bool | None = None
    ) -> dict:
        self.json_requests.append((model, messages, schema, think))
        if self.json_reply is None:
            raise ProviderError(f"{self.name}: no structured output")
        return self.json_reply


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
    # Jamais d'appel aux benchmarks en ligne pendant les tests, même avec une clé dans le .env.
    app.dependency_overrides[get_benchmarks_client] = lambda: None

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
    """Un dossier jetable, à la place de votre dossier personnel, pendant le test en cours.

    Il sert à la fois de dossier atteignable et d'ancien dossier de travail.
    """
    root = tmp_path / "workspace"
    root.mkdir()
    app.dependency_overrides[get_workspace] = lambda: Workspace(root)
    app.dependency_overrides[get_reach] = lambda: Workspace(root)
    return root


@pytest.fixture
def approvals() -> ApprovalRegistry:
    """Un registre d'autorisations neuf pour le test en cours, avec une attente courte."""
    registry = ApprovalRegistry(timeout=5.0)
    app.dependency_overrides[get_approvals] = lambda: registry
    return registry


def parse_sse(body: str) -> list[tuple[str, dict]]:
    """Transforme un corps SSE brut en liste de paires (événement, données)."""
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events
