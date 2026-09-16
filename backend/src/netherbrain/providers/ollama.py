import json
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx

from netherbrain.providers.base import ProviderError, parse_json_object
from netherbrain.providers.catalog import card_from_ollama
from netherbrain.providers.openai_compatible import OpenAICompatibleProvider
from netherbrain.schemas import (
    ChatMessage,
    ModelCard,
    ReasoningEvent,
    StreamEvent,
    TokenEvent,
    ToolCallEvent,
    UsageEvent,
)


class OllamaProvider(OpenAICompatibleProvider):
    """Ollama, à travers son API native plutôt que sa façade compatible OpenAI.

    La façade compatible OpenAI ignore les options du moteur : les modèles sont alors
    chargés avec le contexte par défaut d'Ollama (4096 tokens), bien trop court dès que
    l'agent lit des fichiers. L'API native accepte `num_ctx`, décrit les modèles en détail
    (taille, quantification, capacités) et sépare la réflexion de la réponse.
    """

    def __init__(
        self,
        base_url: str,
        name: str = "ollama",
        *,
        context_length: int = 0,
        chat_timeout: float = 600.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(name, base_url, local=True)
        # http://localhost:11434/v1 → http://localhost:11434
        self._native_url = base_url.rstrip("/").removesuffix("/v1")
        self._context_length = context_length
        self._chat_timeout = chat_timeout
        # Les tests remplacent le réseau par des réponses préparées à l'avance.
        self._transport = transport

    async def describe_models(self) -> list[ModelCard]:
        try:
            async with httpx.AsyncClient(timeout=10, transport=self._transport) as client:
                response = await client.get(f"{self._native_url}/api/tags")
                response.raise_for_status()
        except httpx.ConnectError as exc:
            # Le cas le plus courant : Ollama n'est tout simplement pas lancé.
            raise ProviderError(
                f"{self.name}: not running (cannot reach {self._native_url})"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name}: {str(exc) or type(exc).__name__}") from exc
        cards = [card_from_ollama(self.name, raw) for raw in response.json().get("models", [])]
        return sorted(cards, key=lambda card: card.id)

    async def list_models(self) -> list[str]:
        # Les modèles d'embeddings ne savent pas discuter : on ne les propose pas au chat.
        cards = await self.describe_models()
        return [card.id for card in cards if "embedding" not in card.capabilities]

    async def stream_chat(
        self,
        model: str,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Streame la réponse par `/api/chat`, une ligne de JSON par morceau généré."""
        payload: dict[str, Any] = {
            "model": model,
            "messages": [native_message(message) for message in messages],
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
        if self._context_length:
            # La fenêtre de contexte demandée au moteur : tout ce qui dépasse serait oublié.
            payload["options"] = {"num_ctx": self._context_length}

        try:
            async with (
                httpx.AsyncClient(timeout=self._chat_timeout, transport=self._transport) as client,
                client.stream("POST", f"{self._native_url}/api/chat", json=payload) as response,
            ):
                if response.status_code >= 400:
                    detail = (await response.aread()).decode(errors="replace")[:200]
                    raise ProviderError(f"{self.name}: HTTP {response.status_code}: {detail}")
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if error := chunk.get("error"):
                        raise ProviderError(f"{self.name}: {error}")
                    for event in stream_events(chunk):
                        yield event
        except httpx.ConnectError as exc:
            # Le cas le plus courant : Ollama n'est tout simplement pas lancé.
            raise ProviderError(
                f"{self.name}: not running (cannot reach {self._native_url})"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name}: {str(exc) or type(exc).__name__}") from exc

    async def loaded_models(self) -> list[str]:
        """Les modèles chargés en VRAM en ce moment (GET /api/ps) ; vide en cas d'erreur."""
        try:
            async with httpx.AsyncClient(timeout=3, transport=self._transport) as client:
                response = await client.get(f"{self._native_url}/api/ps")
                response.raise_for_status()
                return [model["name"] for model in response.json().get("models", [])]
        except httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError:
            return []

    async def complete_json(
        self,
        model: str,
        messages: list[ChatMessage],
        schema: dict[str, Any],
        *,
        think: bool | None = None,
    ) -> dict[str, Any]:
        """Sortie structurée d'Ollama : `format` reçoit le schéma JSON, qu'il fait respecter.

        Ollama contraint la génération token par token : la réponse est forcément du JSON
        conforme. `think=False` coupe la réflexion des modèles qui raisonnent (plus rapide).
        """
        # Le même contexte que pour discuter : un autre ferait recharger le modèle en VRAM.
        options: dict[str, Any] = {"temperature": 0}
        if self._context_length:
            options["num_ctx"] = self._context_length
        payload: dict[str, Any] = {
            "model": model,
            "messages": [native_message(message) for message in messages],
            "stream": False,
            "format": schema,
            "options": options,
        }
        if think is not None:
            payload["think"] = think

        try:
            async with httpx.AsyncClient(
                timeout=self._chat_timeout, transport=self._transport
            ) as client:
                response = await client.post(f"{self._native_url}/api/chat", json=payload)
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"{self.name}: not running (cannot reach {self._native_url})"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name}: {str(exc) or type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise ProviderError(f"{self.name}: HTTP {response.status_code}: {response.text[:200]}")
        message = response.json().get("message") or {}
        return parse_json_object(self.name, message.get("content") or "")


def native_message(message: ChatMessage) -> dict[str, Any]:
    """Un message au format d'Ollama : les arguments d'outils y sont des objets, pas du texte."""
    payload: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "function": {
                    "name": call["function"]["name"],
                    "arguments": as_object(call["function"]["arguments"]),
                }
            }
            for call in message.tool_calls
        ]
    return payload


def as_object(arguments: Any) -> dict[str, Any]:
    """Les arguments d'un appel d'outil, quel que soit le format d'où ils viennent."""
    if isinstance(arguments, dict):
        return arguments
    try:
        parsed = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def stream_events(chunk: dict[str, Any]) -> Iterator[StreamEvent]:
    """Traduit un morceau du stream d'Ollama en événements communs à tous les fournisseurs."""
    message = chunk.get("message") or {}
    if thinking := message.get("thinking"):
        yield ReasoningEvent(content=thinking)
    if content := message.get("content"):
        yield TokenEvent(content=content)
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        yield ToolCallEvent(
            # Ollama ne numérote pas toujours ses appels ; l'identifiant sert aux autorisations.
            id=call.get("id") or f"call_{uuid.uuid4().hex[:8]}",
            name=function.get("name", ""),
            arguments=json.dumps(function.get("arguments") or {}),
        )
    if chunk.get("done"):
        yield UsageEvent(
            prompt_tokens=chunk.get("prompt_eval_count") or 0,
            completion_tokens=chunk.get("eval_count") or 0,
        )
