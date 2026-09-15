"""Retrouver, parmi les fichiers d'une conversation, les extraits utiles à une question."""

import uuid

from netherbrain.db.repository import DocumentRepository
from netherbrain.rag.embeddings import Embedder, EmbeddingError
from netherbrain.schemas import Source


async def find_sources(
    question: str,
    embedder: Embedder,
    documents: DocumentRepository,
    limit: int,
    conversation_id: uuid.UUID,
    attachment_ids: list[uuid.UUID],
) -> tuple[list[Source], str | None]:
    """Les extraits les plus proches de la question, ou un avertissement si c'est impossible.

    Dégradation gracieuse : si le modèle d'embeddings est indisponible, on répond quand
    même, et on le signale.
    """
    try:
        vector = await embedder.embed_query(question)
    except EmbeddingError as exc:
        return [], f"Search unavailable: {exc}"
    return await documents.search(vector, limit, conversation_id, attachment_ids), None
