"""Routes des fichiers joints à une conversation : joindre (puis lire en tâche de fond),
lister, afficher une image, retirer."""

import uuid
from typing import Annotated

import anyio
from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Response, UploadFile, status

from netherbrain.api.deps import DbSession, EmbedderDep, SessionFactory, SettingsDep
from netherbrain.db.repository import ConversationRepository, DocumentRepository
from netherbrain.rag.extract import UnsupportedDocumentError, content_type_for, image_type
from netherbrain.rag.ingest import ingest_document
from netherbrain.schemas import AttachmentInfo

router = APIRouter(prefix="/api/conversations/{conversation_id}/attachments", tags=["attachments"])


async def conversation_or_404(session: DbSession, conversation_id: uuid.UUID) -> None:
    if not await ConversationRepository(session).exists(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")


@router.get("")
async def list_attachments(conversation_id: uuid.UUID, session: DbSession) -> list[AttachmentInfo]:
    """Les fichiers de la conversation, envoyés ou encore en attente dans la zone de saisie."""
    await conversation_or_404(session, conversation_id)
    documents = await DocumentRepository(session).list_for(conversation_id)
    return [AttachmentInfo.model_validate(d) for d in documents]


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def attach_file(
    conversation_id: uuid.UUID,
    file: UploadFile,
    background: BackgroundTasks,
    session: DbSession,
    session_factory: SessionFactory,
    embedder: EmbedderDep,
    settings: SettingsDep,
    # Chemin du fichier dans le dossier joint, pour l'afficher (jamais utilisé sur le disque).
    path: Annotated[str | None, Form(max_length=1024)] = None,
) -> AttachmentInfo:
    """Joint un fichier ; sa lecture continue en tâche de fond.

    202 Accepted : la demande est acceptée, mais le traitement n'est pas fini. Le client
    suit l'avancement grâce au statut du fichier (processing, puis ready ou error). Une
    image, elle, n'a rien à lire : elle est gardée telle quelle et prête tout de suite.
    """
    await conversation_or_404(session, conversation_id)
    name = file.filename or "file"

    # On lit au plus un octet de trop : suffisant pour savoir que la limite est dépassée,
    # sans charger en mémoire un fichier énorme.
    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"{name} is too large (max {settings.max_upload_mb} MB)",
        )
    try:
        # Vérifier que 20 Mo sont bien du texte UTF-8 prend un peu de calcul : dans un thread.
        content_type = await anyio.to_thread.run_sync(content_type_for, name, data)
    except UnsupportedDocumentError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)) from exc

    repository = DocumentRepository(session)
    if image_type(data):
        document = await repository.create(
            conversation_id, name[:255], content_type, len(data), path=path, data=data
        )
        await session.commit()
        return AttachmentInfo.model_validate(document)

    document = await repository.create(
        conversation_id, name[:255], content_type, len(data), path=path
    )
    await session.commit()

    background.add_task(
        ingest_document,
        document.id,
        data,
        content_type,
        session_factory=session_factory,
        embedder=embedder,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        inline_limit=settings.attachment_inline_chars,
    )
    return AttachmentInfo.model_validate(document)


@router.get("/{attachment_id}/content")
async def image_content(
    conversation_id: uuid.UUID, attachment_id: uuid.UUID, session: DbSession
) -> Response:
    """L'image jointe, pour l'afficher dans la conversation."""
    document = await DocumentRepository(session).image(conversation_id, attachment_id)
    if document is None or document.data is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(
        document.data,
        media_type=document.content_type,
        headers={
            # Un fichier joint ne change jamais : le navigateur peut le garder indéfiniment.
            "Cache-Control": "private, max-age=31536000, immutable",
            # Le navigateur s'en tient au type annoncé, sans deviner autre chose.
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_attachment(
    conversation_id: uuid.UUID, attachment_id: uuid.UUID, session: DbSession
) -> None:
    if not await DocumentRepository(session).delete(conversation_id, attachment_id):
        raise HTTPException(status_code=404, detail="Attachment not found")
    await session.commit()
