from collections.abc import AsyncIterator
from typing import Any, Protocol

from netherbrain.schemas import ChatMessage, ModelCard, StreamEvent


class ProviderError(Exception):
    """Levée quand un fournisseur est injoignable ou refuse une requête."""


class LLMProvider(Protocol):
    """Ce que le reste de l'application attend de n'importe quel backend de LLM.

    La couche API ne dépend que de cette interface, jamais d'un fournisseur concret :
    ajouter un backend, c'est écrire une nouvelle classe, sans toucher aux routes.
    """

    name: str
    # True si les modèles tournent sur cette machine : ils se partagent alors le même GPU.
    local: bool

    async def list_models(self) -> list[str]: ...

    async def describe_models(self) -> list[ModelCard]: ...

    def stream_chat(
        self,
        model: str,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[StreamEvent]: ...
