"""Indexer un document : extraire le texte, le découper, calculer les vecteurs, enregistrer."""

import logging
import uuid

import anyio
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from netherbrain.db.repository import DocumentRepository
from netherbrain.rag.chunking import chunk_pages
from netherbrain.rag.embeddings import Embedder, EmbeddingError
from netherbrain.rag.extract import UnsupportedDocumentError, extract_pages

logger = logging.getLogger(__name__)


async def ingest_document(
    document_id: uuid.UUID,
    data: bytes,
    content_type: str,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    embedder: Embedder,
    chunk_size: int,
    chunk_overlap: int,
) -> None:
    """Tâche de fond lancée après l'import : le document passe de « processing » à « ready »
    (ou « error », avec la raison)."""
    try:
        # Lire un gros PDF prend du temps de calcul : on le fait dans un thread, pour ne
        # pas bloquer la boucle d'événements (et donc toutes les autres requêtes).
        pages = await anyio.to_thread.run_sync(extract_pages, data, content_type)
        chunks = chunk_pages(pages, chunk_size, chunk_overlap)
        embeddings = await embedder.embed_documents([chunk.content for chunk in chunks])
    except (UnsupportedDocumentError, EmbeddingError) as exc:
        await _mark(session_factory, document_id, status="error", error=str(exc))
        return

    try:
        async with session_factory() as session:
            repository = DocumentRepository(session)
            await repository.add_chunks(document_id, chunks, embeddings)
            await repository.mark(document_id, status="ready", chunk_count=len(chunks))
            await session.commit()
    except SQLAlchemyError, OSError:
        logger.exception("Could not save the chunks of document %s", document_id)
        await _mark(session_factory, document_id, status="error", error="Could not save it")


async def _mark(
    session_factory: async_sessionmaker[AsyncSession], document_id: uuid.UUID, **fields: object
) -> None:
    try:
        async with session_factory() as session:
            await DocumentRepository(session).mark(document_id, **fields)
            await session.commit()
    except SQLAlchemyError, OSError:
        logger.exception("Could not update document %s", document_id)
