"""Retrouver les extraits de documents utiles à une question."""

from netherbrain.db.repository import DocumentRepository
from netherbrain.rag.embeddings import Embedder, EmbeddingError
from netherbrain.schemas import Source


async def find_sources(
    question: str, embedder: Embedder, documents: DocumentRepository, limit: int
) -> tuple[list[Source], str | None]:
    """Les extraits les plus proches de la question, ou un avertissement si c'est impossible.

    Dégradation gracieuse : si le modèle d'embeddings est indisponible, on répond quand
    même, sans les documents, et on le signale.
    """
    try:
        vector = await embedder.embed_query(question)
    except EmbeddingError as exc:
        return [], f"Documents not used: {exc}"
    return await documents.search(vector, limit), None
