"""Ce que le modèle reçoit des fichiers joints à la conversation."""

import uuid
from dataclasses import dataclass, field

from netherbrain.db.repository import DocumentRepository
from netherbrain.rag.embeddings import Embedder
from netherbrain.rag.prompt import build_context, build_files_context
from netherbrain.rag.retrieval import find_sources
from netherbrain.schemas import Source


@dataclass
class AttachmentContext:
    # Le texte à ajouter au message système ; None s'il n'y a aucun fichier joint.
    system: str | None = None
    # Les passages retrouvés, quand les fichiers sont trop longs pour partir en entier.
    sources: list[Source] = field(default_factory=list)
    warning: str | None = None


async def attachment_context(
    conversation_id: uuid.UUID,
    question: str,
    attachment_ids: list[uuid.UUID],
    *,
    documents: DocumentRepository,
    embedder: Embedder,
    inline_limit: int,
    top_k: int,
) -> AttachmentContext:
    """Les fichiers joints : en entier s'ils tiennent dans `inline_limit` caractères.

    Au-delà, on passe au RAG : seuls les passages les plus proches de la question partent.
    Et si la recherche est impossible (modèle d'embeddings absent), on envoie le début des
    fichiers, en le signalant.
    """
    files = await documents.readable(conversation_id, attachment_ids)
    if not files:
        return AttachmentContext()
    if sum(len(text) for _, text in files) <= inline_limit:
        return AttachmentContext(system=build_files_context(files, inline_limit))

    sources, warning = await find_sources(
        question, embedder, documents, top_k, conversation_id, attachment_ids
    )
    if sources:
        return AttachmentContext(system=build_context(sources), sources=sources)
    notice = "The attached files are too long to be sent whole: only their beginning was used."
    return AttachmentContext(
        system=build_files_context(files, inline_limit),
        warning=f"{warning}. {notice}" if warning else notice,
    )
