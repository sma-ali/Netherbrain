from collections.abc import AsyncIterator, Callable
from typing import Any

import openai
from openai import AsyncOpenAI

from netherbrain.providers.base import ProviderError
from netherbrain.providers.catalog import card_from_openai_compatible
from netherbrain.schemas import (
    ChatMessage,
    ModelCard,
    ReasoningEvent,
    StreamEvent,
    TokenEvent,
    ToolCallEvent,
    UsageEvent,
)


def describe_error(exc: openai.APIError) -> str:
    """Un message d'erreur court et lisible, sans le corps JSON complet du fournisseur.

    Ce message est affiché dans l'interface et enregistré en base : le corps brut, lui,
    peut être très long et contenir des informations sur le compte (identifiant, etc.).
    """
    if isinstance(exc, openai.RateLimitError):
        return "rate limit reached, retry in a moment or pick another model"
    if isinstance(exc, openai.APIStatusError):
        error = exc.body.get("error") if isinstance(exc.body, dict) else None
        detail = error.get("message") if isinstance(error, dict) else None
        return f"HTTP {exc.status_code}: {detail}" if detail else f"HTTP {exc.status_code}"
    # Erreurs réseau : « Connection error. », « Request timed out. »
    return exc.message


class OpenAICompatibleProvider:
    """N'importe quel backend qui parle l'API Chat Completions d'OpenAI.

    Ollama, OpenRouter, Groq, vLLM... exposent tous cette API : une seule classe
    les couvre tous, seules l'URL de base et la clé d'API changent.
    """

    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str = "not-needed",
        *,
        model_filter: Callable[[str], bool] | None = None,
        default_headers: dict[str, str] | None = None,
        timeout: float = 60.0,
        local: bool = False,
    ) -> None:
        self.name = name
        self.local = local
        self._model_filter = model_filter
        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            default_headers=default_headers,
            timeout=timeout,
            max_retries=1,
        )

    async def list_models(self) -> list[str]:
        return [card.id for card in await self.describe_models()]

    async def describe_models(self) -> list[ModelCard]:
        try:
            page = await self._client.models.list()
        except openai.APIError as exc:
            raise ProviderError(f"{self.name}: {describe_error(exc)}") from exc
        cards = [
            # model_extra : les champs que le fournisseur ajoute au format standard.
            card_from_openai_compatible(self.name, model.id, model.model_extra or {}, self.local)
            for model in page.data
            if self._model_filter is None or self._model_filter(model.id)
        ]
        return sorted(cards, key=lambda card: card.id)

    async def stream_chat(
        self,
        model: str,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Streame la réponse. Avec `tools`, le modèle peut demander à en utiliser un."""
        # Les appels d'outils arrivent en morceaux, à assembler par numéro d'appel.
        calls: dict[int, dict[str, str]] = {}
        try:
            stream = await self._client.chat.completions.create(
                model=model,
                # exclude_none : un `tool_call_id: null` ferait refuser la requête.
                messages=[message.model_dump(exclude_none=True) for message in messages],
                stream=True,
                stream_options={"include_usage": True},
                **({"tools": tools} if tools else {}),
            )
            async for chunk in stream:
                if chunk.usage:
                    yield UsageEvent(
                        prompt_tokens=chunk.usage.prompt_tokens,
                        completion_tokens=chunk.usage.completion_tokens,
                    )
                for choice in chunk.choices:
                    # « reasoning » ne fait pas partie du schéma officiel d'OpenAI : Ollama
                    # et OpenRouter l'ajoutent pour les modèles qui réfléchissent, d'où getattr.
                    if reasoning := getattr(choice.delta, "reasoning", None):
                        yield ReasoningEvent(content=reasoning)
                    if choice.delta.content:
                        yield TokenEvent(content=choice.delta.content)
                    for fragment in choice.delta.tool_calls or []:
                        call = calls.setdefault(
                            fragment.index, {"id": "", "name": "", "arguments": ""}
                        )
                        if fragment.id:
                            call["id"] = fragment.id
                        if fragment.function and fragment.function.name:
                            call["name"] = fragment.function.name
                        if fragment.function and fragment.function.arguments:
                            call["arguments"] += fragment.function.arguments
        except openai.APIError as exc:
            raise ProviderError(f"{self.name}: {describe_error(exc)}") from exc

        # Les appels complets partent à la fin du stream, dans l'ordre demandé par le modèle.
        for index in sorted(calls):
            call = calls[index]
            yield ToolCallEvent(
                id=call["id"] or f"call_{index}", name=call["name"], arguments=call["arguments"]
            )
