import json
from collections.abc import AsyncIterator
from typing import Any, Protocol

from netherbrain.schemas import ChatMessage, ModelCard, StreamEvent


class ProviderError(Exception):
    """Levée quand un fournisseur est injoignable ou refuse une requête."""


def parse_json_object(provider: str, text: str) -> dict[str, Any]:
    """Le JSON d'une sortie structurée ; ProviderError si le modèle n'a pas respecté le format."""
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"{provider}: the answer is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ProviderError(f"{provider}: the answer is not a JSON object")
    return value


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

    async def complete_json(
        self,
        model: str,
        messages: list[ChatMessage],
        schema: dict[str, Any],
        *,
        think: bool | None = None,
    ) -> dict[str, Any]:
        """Une réponse complète, au format JSON imposé par `schema` (sortie structurée)."""
        ...
