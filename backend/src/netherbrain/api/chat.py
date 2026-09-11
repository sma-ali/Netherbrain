import json
import time
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from netherbrain.api.deps import get_provider
from netherbrain.providers import LLMProvider, ProviderError
from netherbrain.schemas import ChatRequest, ModelInfo, UsageEvent

router = APIRouter(prefix="/api", tags=["chat"])

Provider = Annotated[LLMProvider, Depends(get_provider)]


def sse(event: str, data: dict[str, Any]) -> str:
    """Format one Server-Sent Event: an `event:` line, a `data:` line, a blank line."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/models")
async def list_models(provider: Provider) -> list[ModelInfo]:
    try:
        model_ids = await provider.list_models()
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return [ModelInfo(id=model_id, provider=provider.name) for model_id in model_ids]


@router.post("/chat")
async def chat(request: ChatRequest, provider: Provider) -> StreamingResponse:
    """Stream the answer as Server-Sent Events.

    Event types: `reasoning`, `token`, then either `done` (with metrics) or `error`.
    """

    async def event_stream() -> AsyncIterator[str]:
        started = time.perf_counter()
        first_token_at: float | None = None
        usage: UsageEvent | None = None

        try:
            async for event in provider.stream_chat(request.model, request.messages):
                if isinstance(event, UsageEvent):
                    usage = event
                    continue
                if first_token_at is None:
                    first_token_at = time.perf_counter()
                yield sse(event.type, event.model_dump(exclude={"type"}))
        except ProviderError as exc:
            # The 200 status line is already sent once streaming starts,
            # so errors have to travel inside the stream itself.
            yield sse("error", {"message": str(exc)})
            return

        finished = time.perf_counter()
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
        yield sse("done", metrics)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
