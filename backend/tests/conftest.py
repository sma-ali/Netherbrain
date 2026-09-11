import json
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient

from netherbrain.api.deps import get_provider
from netherbrain.main import app
from netherbrain.providers import ProviderError
from netherbrain.schemas import ChatMessage, StreamEvent


class FakeProvider:
    """Stands in for a real LLM: replays scripted events, no network, no GPU."""

    name = "fake"

    def __init__(self, events: list[StreamEvent] | None = None, fail: bool = False) -> None:
        self.events = events or []
        self.fail = fail
        self.received: list[ChatMessage] = []

    async def list_models(self) -> list[str]:
        if self.fail:
            raise ProviderError("fake: unreachable")
        return ["fake-model"]

    async def stream_chat(
        self, model: str, messages: list[ChatMessage]
    ) -> AsyncIterator[StreamEvent]:
        self.received = messages
        for event in self.events:
            yield event
        if self.fail:
            raise ProviderError("fake: connection lost")


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def use_provider():
    """Install a FakeProvider in place of the real one for the current test."""

    def install(provider: FakeProvider) -> FakeProvider:
        app.dependency_overrides[get_provider] = lambda: provider
        return provider

    return install


def parse_sse(body: str) -> list[tuple[str, dict]]:
    """Turn a raw SSE body into a list of (event, data) pairs."""
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events
