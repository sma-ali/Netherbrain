"""Routes des documents : importer (puis indexer en tâche de fond), lister, supprimer."""

import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, status

from netherbrain.api.deps import DbSession, EmbedderDep, SessionFactory, SettingsDep
from netherbrain.db.repository import DocumentRepository
from netherbrain.rag.extract import UnsupportedDocumentError, content_type_for
from netherbrain.rag.ingest import ingest_document
from netherbrain.schemas import DocumentInfo

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("")
async def list_documents(session: DbSession) -> list[DocumentInfo]:
    documents = await DocumentRepository(session).list_recent()
    return [DocumentInfo.model_validate(d) for d in documents]


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile,
    background: BackgroundTasks,
    session: DbSession,
    session_factory: SessionFactory,
    embedder: EmbedderDep,
    settings: SettingsDep,
) -> DocumentInfo:
    """Importe un fichier ; son indexation continue en tâche de fond.

    202 Accepted : la demande est acceptée, mais le traitement n'est pas fini. Le client
    suit l'avancement grâce au statut du document (processing, puis ready ou error).
    """
    name = file.filename or "document"
    try:
        content_type = content_type_for(name)
    except UnsupportedDocumentError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)) from exc

    # On lit au plus un octet de trop : suffisant pour savoir que la limite est dépassée,
    # sans charger en mémoire un fichier énorme.
    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File too large (max {settings.max_upload_mb} MB)",
        )

    document = await DocumentRepository(session).create(name[:255], content_type, len(data))
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
    )
    return DocumentInfo.model_validate(document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: uuid.UUID, session: DbSession) -> None:
    if not await DocumentRepository(session).delete(document_id):
        raise HTTPException(status_code=404, detail="Document not found")
    await session.commit()
