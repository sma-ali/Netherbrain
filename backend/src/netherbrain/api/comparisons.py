"""Routes des comparaisons : la même question posée à plusieurs modèles, enregistrée."""

import logging
import uuid
from collections.abc import AsyncIterator

import anyio
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError

from netherbrain.api.deps import DbSession, Registry, SessionFactory, get_provider_or_404
from netherbrain.api.streaming import StreamResult, sse_response, stream_answer
from netherbrain.db.models import Comparison
from netherbrain.db.repository import ComparisonRepository
from netherbrain.schemas import (
    ChatMessage,
    ComparisonDetail,
    ComparisonSummary,
    CreateComparisonRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/comparisons", tags=["comparisons"])


async def get_or_404(repository: ComparisonRepository, comparison_id: uuid.UUID) -> Comparison:
    comparison = await repository.get(comparison_id)
    if comparison is None:
        raise HTTPException(status_code=404, detail="Comparison not found")
    return comparison


@router.get("")
async def list_comparisons(session: DbSession) -> list[ComparisonSummary]:
    """Les comparaisons, de la plus récente à la plus ancienne."""
    comparisons = await ComparisonRepository(session).list_recent()
    return [
        ComparisonSummary(
            id=c.id, prompt=c.prompt, created_at=c.created_at, models=[r.model for r in c.results]
        )
        for c in comparisons
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_comparison(
    request: CreateComparisonRequest, registry: Registry, session: DbSession
) -> ComparisonDetail:
    """Crée la comparaison et une réponse « en attente » par modèle.

    Le client lance ensuite chaque réponse séparément, dans l'ordre qu'il veut : il peut
    ainsi faire passer les modèles locaux un par un et les distants en parallèle.
    """
    for contender in request.contenders:
        get_provider_or_404(registry, contender.provider)

    comparison = await ComparisonRepository(session).create(
        request.prompt, [(c.provider, c.model) for c in request.contenders]
    )
    await session.commit()
    return ComparisonDetail.model_validate(comparison)


@router.get("/{comparison_id}")
async def get_comparison(comparison_id: uuid.UUID, session: DbSession) -> ComparisonDetail:
    comparison = await get_or_404(ComparisonRepository(session), comparison_id)
    return ComparisonDetail.model_validate(comparison)


@router.delete("/{comparison_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comparison(comparison_id: uuid.UUID, session: DbSession) -> None:
    if not await ComparisonRepository(session).delete(comparison_id):
        raise HTTPException(status_code=404, detail="Comparison not found")
    await session.commit()


@router.post("/{comparison_id}/results/{result_id}/run")
async def run_result(
    comparison_id: uuid.UUID,
    result_id: uuid.UUID,
    registry: Registry,
    session: DbSession,
    session_factory: SessionFactory,
) -> StreamingResponse:
    """Streame la réponse d'un des modèles de la comparaison, puis l'enregistre."""
    repository = ComparisonRepository(session)
    found = await repository.get_result(comparison_id, result_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Result not found")
    result, prompt = found
    # 409 Conflict : la requête est valide, mais incompatible avec l'état de la ressource.
    if result.state != "pending":
        raise HTTPException(status_code=409, detail="This answer has already been generated")
    provider = get_provider_or_404(registry, result.provider)
    model = result.model

    # Marquer la réponse « en cours » tout de suite : un second lancement échouera (409).
    await repository.save_result(result_id, state="running")
    await session.commit()

    async def event_stream() -> AsyncIterator[str]:
        outcome = StreamResult()
        question = [ChatMessage(role="user", content=prompt)]
        try:
            async for chunk in stream_answer(provider, model, question, outcome):
                yield chunk
        finally:
            # Comme pour le chat : enregistrer même si le client coupe en pleine réponse.
            with anyio.CancelScope(shield=True):
                await save_outcome(session_factory, result_id, outcome)

    return sse_response(event_stream())


async def save_outcome(
    session_factory: SessionFactory, result_id: uuid.UUID, outcome: StreamResult
) -> None:
    state = "done" if outcome.finished else "error" if outcome.error else "stopped"
    try:
        async with session_factory() as session:
            await ComparisonRepository(session).save_result(
                result_id,
                state=state,
                content=outcome.content,
                reasoning=outcome.reasoning or None,
                metrics=outcome.metrics,
                error=outcome.error,
            )
            await session.commit()
    except SQLAlchemyError, OSError:
        # La réponse est déjà partie : impossible de prévenir le client, on journalise.
        logger.exception("Could not save comparison result %s", result_id)
