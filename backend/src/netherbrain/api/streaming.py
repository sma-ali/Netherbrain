"""Le cœur du streaming : relayer les événements d'un fournisseur en Server-Sent Events."""

import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from fastapi.responses import StreamingResponse

from netherbrain.providers import LLMProvider, ProviderError
from netherbrain.schemas import ChatMessage, TokenEvent, UsageEvent


@dataclass
class StreamResult:
    """Ce qui a été généré, accumulé au fil du stream pour pouvoir l'enregistrer ensuite."""

    content: str = ""
    reasoning: str = ""
    metrics: dict[str, Any] | None = None
    error: str | None = None
    finished: bool = False


def sse(event: str, data: dict[str, Any]) -> str:
    """Formate un Server-Sent Event : une ligne `event:`, une ligne `data:`, une ligne vide."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def sse_response(stream: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        # Désactive les caches et les tampons des proxys : chaque événement part aussitôt.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def stream_answer(
    provider: LLMProvider, model: str, messages: list[ChatMessage], result: StreamResult
) -> AsyncIterator[str]:
    """Streame la réponse du modèle sous forme de Server-Sent Events.

    Types d'événements : `reasoning`, `token`, puis `done` (avec les métriques)
    ou `error`. Au passage, `result` accumule ce qui a été généré.
    """
    started = time.perf_counter()
    first_token_at: float | None = None
    usage: UsageEvent | None = None

    try:
        async for event in provider.stream_chat(model, messages):
            if isinstance(event, UsageEvent):
                usage = event
                continue
            if first_token_at is None:
                first_token_at = time.perf_counter()
            if isinstance(event, TokenEvent):
                result.content += event.content
            else:
                result.reasoning += event.content
            yield sse(event.type, event.model_dump(exclude={"type"}))
    except ProviderError as exc:
        # Une fois le stream commencé, le statut 200 est déjà parti :
        # les erreurs doivent donc voyager à l'intérieur du stream.
        result.error = str(exc)
        yield sse("error", {"message": result.error})
        return

    result.metrics = compute_metrics(started, first_token_at, time.perf_counter(), usage)
    result.finished = True
    yield sse("done", result.metrics)


def compute_metrics(
    started: float, first_token_at: float | None, finished: float, usage: UsageEvent | None
) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "total_ms": round((finished - started) * 1000),
        "ttft_ms": round((first_token_at - started) * 1000) if first_token_at else None,
    }
    if usage:
        generation_s = finished - (first_token_at or started)
        metrics["prompt_tokens"] = usage.prompt_tokens
        metrics["completion_tokens"] = usage.completion_tokens
        metrics["tokens_per_second"] = (
            round(usage.completion_tokens / generation_s, 1) if generation_s > 0 else None
        )
    return metrics
