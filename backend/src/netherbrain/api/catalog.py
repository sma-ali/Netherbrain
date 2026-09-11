"""Le catalogue : une fiche par modèle, avec ce que Netherbrain a mesuré en l'utilisant."""

import logging

from fastapi import APIRouter
from sqlalchemy.exc import SQLAlchemyError

from netherbrain.api.chat import provider_statuses
from netherbrain.api.deps import Registry, SessionFactory
from netherbrain.db.repository import model_stats
from netherbrain.schemas import CatalogResponse, ModelStats

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/catalog")
async def catalog(registry: Registry, session_factory: SessionFactory) -> CatalogResponse:
    """Les fiches de tous les modèles disponibles, avec leurs mesures réelles.

    Les mesures viennent de la base : si elle est indisponible, le catalogue s'affiche
    quand même, sans elles (dégradation gracieuse).
    """
    results = await registry.describe_all()

    stats: dict[tuple[str, str], ModelStats] = {}
    stats_available = True
    try:
        async with session_factory() as session:
            stats = await model_stats(session)
    except SQLAlchemyError, OSError:
        logger.warning("Model statistics unavailable", exc_info=True)
        stats_available = False

    return CatalogResponse(
        models=[
            card.model_copy(update={"stats": stats.get((card.provider, card.id))})
            for r in results
            for card in r.items
        ],
        providers=provider_statuses(results),
        stats_available=stats_available,
    )
