import asyncio
import json
import os
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool, StaticPool

from netherbrain.api.deps import get_registry, get_session_factory
from netherbrain.db.models import Base
from netherbrain.main import app
from netherbrain.providers import ProviderError, ProviderRegistry
from netherbrain.schemas import ChatMessage, StreamEvent

# Par défaut, les tests tournent sur SQLite en mémoire : rapide, rien à installer.
# La CI les relance sur un vrai PostgreSQL en définissant cette variable.
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
    ) -> None:
        self.name = name
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

    async def stream_chat(
        self, model: str, messages: list[ChatMessage]
    ) -> AsyncIterator[StreamEvent]:
        self.received = messages
        for scripted in self.events:
            yield scripted
        if self.fail:
            raise ProviderError(f"{self.name}: connection lost")


def make_test_engine(url: str) -> AsyncEngine:
    if not url.startswith("sqlite"):
        # NullPool : aucune connexion gardée entre deux tests (chacun a sa boucle d'événements).
        return create_async_engine(url, poolclass=NullPool)

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


def parse_sse(body: str) -> list[tuple[str, dict]]:
    """Transforme un corps SSE brut en liste de paires (événement, données)."""
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events
