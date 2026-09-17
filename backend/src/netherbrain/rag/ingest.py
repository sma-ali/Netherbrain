"""Lire un fichier joint : extraire le texte, le découper, calculer les vecteurs, enregistrer."""

import logging
import uuid

import anyio
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from netherbrain.db.repository import DocumentRepository
from netherbrain.rag.chunking import chunk_pages
from netherbrain.rag.embeddings import Embedder, EmbeddingError
from netherbrain.rag.extract import UnsupportedDocumentError, extract_pages, pages_to_text

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
    inline_limit: int,
) -> None:
    """Tâche de fond lancée après l'import : le fichier passe de « processing » à « ready »
    (ou « error », avec la raison).

    Le texte est toujours enregistré en entier. Les vecteurs, eux, sont calculés au mieux :
    sans modèle d'embeddings, un petit fichier reste utilisable puisqu'il part en entier au
    modèle ; un gros, en revanche, ne pourrait plus être ni envoyé ni fouillé.
    """
    try:
        # Lire un gros PDF prend du temps de calcul : on le fait dans un thread, pour ne
        # pas bloquer la boucle d'événements (et donc toutes les autres requêtes).
        pages = await anyio.to_thread.run_sync(extract_pages, data, content_type)
    except UnsupportedDocumentError as exc:
        await _mark(session_factory, document_id, status="error", error=str(exc))
        return

    text = pages_to_text(pages)
    chunks = chunk_pages(pages, chunk_size, chunk_overlap)
    try:
        embeddings = await embedder.embed_documents([chunk.content for chunk in chunks])
    except EmbeddingError as exc:
        if len(text) > inline_limit:
            await _mark(
                session_factory,
                document_id,
                status="error",
                error=f"Too long to be sent whole, and search is unavailable: {exc}",
            )
            return
        # Petit fichier : il sera envoyé en entier, la recherche ne lui manquera pas.
        chunks, embeddings = [], []

    try:
        async with session_factory() as session:
            repository = DocumentRepository(session)
            await repository.add_chunks(document_id, chunks, embeddings)
            await repository.mark(
                document_id, status="ready", content=text, chunk_count=len(chunks)
            )
            await session.commit()
    except SQLAlchemyError, OSError:
        logger.exception("Could not save the text of document %s", document_id)
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
