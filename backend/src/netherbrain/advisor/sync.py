"""Garder les benchmarks à jour en base, sans dépasser la limite de requêtes de la source."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from netherbrain.advisor.sources import (
    SOURCE,
    ArtificialAnalysisClient,
    BenchmarkEntry,
    BenchmarkError,
)
from netherbrain.db.repository import BenchmarkRepository

logger = logging.getLogger(__name__)


async def sync_benchmarks(
    client: ArtificialAnalysisClient, session_factory: async_sessionmaker[AsyncSession]
) -> int:
    """Récupère tous les benchmarks et remplace ceux gardés en base. Renvoie leur nombre."""
    entries = await client.fetch()
    if not entries:
        # Une réponse vide ne doit pas effacer des données encore utiles.
        raise BenchmarkError("Artificial Analysis returned no models")
    async with session_factory() as session:
        await BenchmarkRepository(session).replace(SOURCE, entries)
        await session.commit()
    return len(entries)


async def sync_quietly(
    client: ArtificialAnalysisClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """La même chose, en tâche de fond : les erreurs sont journalisées, sans rien casser."""
    try:
        count = await sync_benchmarks(client, session_factory)
        logger.info("Benchmarks refreshed: %d models", count)
    except (BenchmarkError, SQLAlchemyError, OSError) as exc:
        logger.warning("Could not refresh the benchmarks: %s", exc)


async def load_benchmarks(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[list[BenchmarkEntry], datetime | None]:
    async with session_factory() as session:
        repository = BenchmarkRepository(session)
        return await repository.entries(SOURCE), await repository.fetched_at(SOURCE)


def is_stale(
    fetched_at: datetime | None, max_age_hours: float, now: datetime | None = None
) -> bool:
    if fetched_at is None:
        return True
    if fetched_at.tzinfo is None:
        # SQLite ne garde pas le fuseau horaire : les dates y sont enregistrées en UTC.
        fetched_at = fetched_at.replace(tzinfo=UTC)
    return (now or datetime.now(UTC)) - fetched_at > timedelta(hours=max_age_hours)
