from collections.abc import AsyncIterator, Callable

import openai
from openai import AsyncOpenAI

from netherbrain.providers.base import ProviderError
from netherbrain.schemas import ChatMessage, ReasoningEvent, StreamEvent, TokenEvent, UsageEvent


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
    ) -> None:
        self.name = name
        self._model_filter = model_filter
        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            default_headers=default_headers,
            timeout=timeout,
            max_retries=1,
        )

    async def list_models(self) -> list[str]:
        try:
            page = await self._client.models.list()
        except openai.APIError as exc:
            raise ProviderError(f"{self.name}: {exc}") from exc
        return sorted(
            model.id
            for model in page.data
            if self._model_filter is None or self._model_filter(model.id)
        )

    async def stream_chat(
        self, model: str, messages: list[ChatMessage]
    ) -> AsyncIterator[StreamEvent]:
        try:
            stream = await self._client.chat.completions.create(
                model=model,
                messages=[message.model_dump() for message in messages],
                stream=True,
                stream_options={"include_usage": True},
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
        except openai.APIError as exc:
            raise ProviderError(f"{self.name}: {exc}") from exc
