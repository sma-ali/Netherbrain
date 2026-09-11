import json
import time
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from netherbrain.api.deps import get_registry
from netherbrain.providers import ProviderError, ProviderRegistry, UnknownProviderError
from netherbrain.schemas import (
    ChatRequest,
    ModelInfo,
    ModelsResponse,
    ProviderStatus,
    UsageEvent,
)

router = APIRouter(prefix="/api", tags=["chat"])

Registry = Annotated[ProviderRegistry, Depends(get_registry)]


def sse(event: str, data: dict[str, Any]) -> str:
    """Formate un Server-Sent Event : une ligne `event:`, une ligne `data:`, une ligne vide."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/models")
async def list_models(registry: Registry) -> ModelsResponse:
    """Les modèles de tous les fournisseurs, plus l'état de chacun.

    Répond toujours 200 : un fournisseur injoignable apparaît comme indisponible
    au lieu de faire échouer toute la requête.
    """
    results = await registry.list_all()
    return ModelsResponse(
        models=[ModelInfo(id=model, provider=r.name) for r in results for model in r.models],
        providers=[
            ProviderStatus(name=r.name, available=r.error is None, error=r.error) for r in results
        ],
    )


@router.post("/chat")
async def chat(request: ChatRequest, registry: Registry) -> StreamingResponse:
    """Streame la réponse sous forme de Server-Sent Events.

    Types d'événements : `reasoning`, `token`, puis `done` (avec les métriques)
    ou `error`.
    """
    try:
        provider = registry.get(request.provider)
    except UnknownProviderError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown provider '{request.provider}'. Available: {', '.join(registry.names)}",
        ) from exc

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
            # Une fois le stream commencé, le statut 200 est déjà parti :
            # les erreurs doivent donc voyager à l'intérieur du stream.
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
