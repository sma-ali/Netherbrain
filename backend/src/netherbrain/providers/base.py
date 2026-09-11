from collections.abc import AsyncIterator
from typing import Protocol

from netherbrain.schemas import ChatMessage, StreamEvent


class ProviderError(Exception):
    """Raised when a provider is unreachable or rejects a request."""


class LLMProvider(Protocol):
    """What the rest of the app expects from any LLM backend.

    The API layer only depends on this interface, never on a concrete provider:
    adding a new backend means writing a new class, not touching the routes.
    """

    name: str

    async def list_models(self) -> list[str]: ...

    def stream_chat(
        self, model: str, messages: list[ChatMessage]
    ) -> AsyncIterator[StreamEvent]: ...
