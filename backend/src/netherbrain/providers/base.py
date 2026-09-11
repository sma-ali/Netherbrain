from collections.abc import AsyncIterator
from typing import Protocol

from netherbrain.schemas import ChatMessage, StreamEvent


class ProviderError(Exception):
    """Levée quand un fournisseur est injoignable ou refuse une requête."""


class LLMProvider(Protocol):
    """Ce que le reste de l'application attend de n'importe quel backend de LLM.

    La couche API ne dépend que de cette interface, jamais d'un fournisseur concret :
    ajouter un backend, c'est écrire une nouvelle classe, sans toucher aux routes.
    """

    name: str

    async def list_models(self) -> list[str]: ...

    def stream_chat(
        self, model: str, messages: list[ChatMessage]
    ) -> AsyncIterator[StreamEvent]: ...
