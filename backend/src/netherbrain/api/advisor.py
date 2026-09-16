"""Le conseiller : quel modèle choisir pour ce que l'utilisateur veut faire."""

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from netherbrain.advisor.matching import BenchmarkIndex
from netherbrain.advisor.needs import needs_from_keywords
from netherbrain.advisor.scoring import Role, Scored, build_candidates, recommend_models
from netherbrain.advisor.sources import SOURCE_NAME, SOURCE_URL, BenchmarkError
from netherbrain.advisor.sync import is_stale, load_benchmarks, sync_benchmarks, sync_quietly
from netherbrain.advisor.understand import pick_advisor_model, understand
from netherbrain.api.deps import BenchmarksClientDep, Registry, SessionFactory, SettingsDep
from netherbrain.config import Settings
from netherbrain.db.repository import model_stats
from netherbrain.providers import (
    ProviderError,
    ProviderRegistry,
    ProviderResult,
    UnknownProviderError,
)
from netherbrain.schemas import (
    BenchmarksStatus,
    ModelCard,
    ModelPick,
    ModelStats,
    Needs,
    Recommendation,
    RecommendRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/advisor", tags=["advisor"])


@router.get("/benchmarks")
async def benchmarks_status(
    session_factory: SessionFactory, client: BenchmarksClientDep
) -> BenchmarksStatus:
    """Où en sont les benchmarks en ligne : configurés ou non, combien de modèles, quand."""
    entries, fetched_at = await load_benchmarks(session_factory)
    return _status(client is not None, len(entries), fetched_at)


@router.post("/benchmarks/sync")
async def refresh_benchmarks(
    session_factory: SessionFactory, client: BenchmarksClientDep
) -> BenchmarksStatus:
    """Met à jour les benchmarks tout de suite, sans attendre qu'ils soient périmés."""
    if client is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Live benchmarks are off: set NETHERBRAIN_ARTIFICIAL_ANALYSIS_API_KEY",
        )
    try:
        await sync_benchmarks(client, session_factory)
    except BenchmarkError as exc:
        # 502 Bad Gateway : c'est le service distant qui a échoué, pas notre API.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    entries, fetched_at = await load_benchmarks(session_factory)
    return _status(True, len(entries), fetched_at)


@router.post("/recommend")
async def recommend(
    request: RecommendRequest,
    registry: Registry,
    session_factory: SessionFactory,
    settings: SettingsDep,
    client: BenchmarksClientDep,
    background: BackgroundTasks,
) -> Recommendation:
    """Comprend la demande, puis classe les modèles et renvoie le podium, avec ses raisons.

    Tout se dégrade proprement : sans base, pas de mesures ; sans benchmarks en ligne, la
    grille seule ; sans modèle pour comprendre la demande, des mots-clés.
    """
    results = await registry.describe_all()
    cards = [card for result in results for card in result.items]
    local_up = any(result.local and result.error is None for result in results)

    stats: dict[tuple[str, str], ModelStats] = {}
    entries, fetched_at, database_up = [], None, True
    try:
        async with session_factory() as session:
            stats = await model_stats(session)
        entries, fetched_at = await load_benchmarks(session_factory)
    except SQLAlchemyError, OSError:
        logger.warning("Advisor without the database", exc_info=True)
        database_up = False

    sync_error = None
    if client is not None and database_up:
        if not entries:
            # Premier usage : on attend les benchmarks, pour que ce conseil en profite déjà.
            try:
                await sync_benchmarks(client, session_factory)
                entries, fetched_at = await load_benchmarks(session_factory)
            except BenchmarkError as exc:
                sync_error = str(exc)
            except SQLAlchemyError:
                # Une autre requête les enregistrait au même moment : on relit simplement.
                entries, fetched_at = await load_benchmarks(session_factory)
        elif is_stale(fetched_at, settings.benchmarks_max_age_hours):
            # Déjà en base mais périmés : on répond tout de suite, la mise à jour suit.
            background.add_task(sync_quietly, client, session_factory)

    if request.understand:
        needs, understood_by = await _understand(request.query, results, registry, settings)
    else:
        needs, understood_by = needs_from_keywords(request.query), "keywords"
    index = BenchmarkIndex(entries) if entries else None
    candidates = build_candidates(cards, stats, index, suggest_downloads=local_up)
    picks = recommend_models(needs, candidates, settings.gpu_vram_gb)

    warnings = []
    if not local_up:
        warnings.append("Ollama is not running: your local models are left out.")
    return Recommendation(
        query=request.query,
        needs=needs,
        understood_by=understood_by,
        picks=[_pick(role, scored) for role, scored in picks],
        benchmarks=_status(client is not None, len(entries), fetched_at, sync_error),
        warnings=warnings,
    )


async def _understand(
    query: str,
    results: list[ProviderResult[ModelCard]],
    registry: ProviderRegistry,
    settings: Settings,
) -> tuple[Needs, str]:
    """Les besoins lus par un LLM, ou déduits des mots-clés si c'est impossible."""
    loaded: set[str] = set()
    for name in registry.names:
        # Seul Ollama sait dire quels modèles sont chargés : les autres n'ont pas la méthode.
        if loaded_models := getattr(registry.get(name), "loaded_models", None):
            loaded.update(await loaded_models())

    advisor = pick_advisor_model(results, settings.advisor_model, frozenset(loaded))
    if advisor is not None:
        try:
            provider = registry.get(advisor.provider)
            # Un modèle local peut mettre du temps à se charger en VRAM : au-delà, les mots-clés.
            async with asyncio.timeout(settings.advisor_timeout):
                needs = await understand(query, provider, advisor)
            return needs, advisor.model
        except (UnknownProviderError, ProviderError, TimeoutError, ValidationError) as exc:
            logger.warning("Request read from keywords, %s failed: %s", advisor.model, exc)
    return needs_from_keywords(query), "keywords"


def _pick(role: Role, scored: Scored) -> ModelPick:
    candidate = scored.candidate
    return ModelPick(
        role=role,
        provider=candidate.provider,
        model=candidate.model,
        local=candidate.local,
        ready=candidate.ready,
        score=round(scored.score, 3),
        reasons=scored.reasons,
        warnings=scored.warnings,
        pull_command=None if candidate.ready else f"ollama pull {candidate.model}",
        benchmark=candidate.benchmark.name if candidate.benchmark else None,
    )


def _status(configured, models, fetched_at, error=None) -> BenchmarksStatus:
    return BenchmarksStatus(
        source=SOURCE_NAME,
        url=SOURCE_URL,
        configured=configured,
        models=models,
        fetched_at=fetched_at,
        error=error,
    )
