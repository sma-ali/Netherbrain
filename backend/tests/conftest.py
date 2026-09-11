import asyncio
import json
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient

from netherbrain.api.deps import get_registry
from netherbrain.main import app
from netherbrain.providers import ProviderError, ProviderRegistry
from netherbrain.schemas import ChatMessage, StreamEvent


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
        for event in self.events:
            yield event
        if self.fail:
            raise ProviderError(f"{self.name}: connection lost")


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(app)
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
