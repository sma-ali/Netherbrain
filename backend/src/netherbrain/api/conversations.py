"""Routes des conversations enregistrées : lister, créer, lire, supprimer, discuter."""

import logging
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import anyio
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError

from netherbrain.agent.tools import Toolbox
from netherbrain.api.deps import (
    ApprovalsDep,
    DbSession,
    EmbedderDep,
    Registry,
    SessionFactory,
    SettingsDep,
    WorkspaceDep,
    get_provider_or_404,
)
from netherbrain.api.streaming import (
    StreamResult,
    sse,
    sse_response,
    stream_agent,
    stream_answer,
)
from netherbrain.db.models import Conversation
from netherbrain.db.repository import (
    ConversationRepository,
    DocumentRepository,
    ProjectRepository,
    make_title,
)
from netherbrain.projects.prompt import build_project_context
from netherbrain.projects.workspace import Workspace
from netherbrain.rag.prompt import build_context
from netherbrain.rag.retrieval import find_sources
from netherbrain.schemas import (
    ApprovalRequest,
    ChatMessage,
    ConversationDetail,
    ConversationSummary,
    CreateConversationRequest,
    SendMessageRequest,
    Source,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


async def get_or_404(
    repository: ConversationRepository, conversation_id: uuid.UUID
) -> Conversation:
    conversation = await repository.get(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


async def project_of(
    session: DbSession, conversation: Conversation, workspace: Workspace
) -> tuple[str, Path] | None:
    """Le nom et le dossier du projet de la conversation, si son dossier existe encore."""
    if conversation.project_id is None:
        return None
    project = await ProjectRepository(session).get(conversation.project_id)
    folder = workspace.find(project.path) if project else None
    return (project.name, folder) if project and folder else None


@router.get("")
async def list_conversations(session: DbSession) -> list[ConversationSummary]:
    """Les conversations, de la plus récemment active à la plus ancienne."""
    conversations = await ConversationRepository(session).list_recent()
    return [ConversationSummary.model_validate(c) for c in conversations]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    session: DbSession, request: CreateConversationRequest | None = None
) -> ConversationSummary:
    """Crée une conversation, rattachée à un projet si on le demande. Le corps est facultatif."""
    project_id = request.project_id if request else None
    # Vérifié ici : sinon la clé étrangère refuserait l'insertion, avec une erreur moins claire.
    if project_id is not None and await ProjectRepository(session).get(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    conversation = await ConversationRepository(session).create(project_id=project_id)
    await session.commit()
    return ConversationSummary.model_validate(conversation)


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: uuid.UUID, session: DbSession) -> ConversationDetail:
    conversation = await get_or_404(ConversationRepository(session), conversation_id)
    return ConversationDetail.model_validate(conversation)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID, session: DbSession, approvals: ApprovalsDep
) -> None:
    if not await ConversationRepository(session).delete(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    # Les outils autorisés « pour toute la conversation » disparaissent avec elle.
    approvals.forget(conversation_id)
    await session.commit()


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: uuid.UUID,
    request: SendMessageRequest,
    registry: Registry,
    session: DbSession,
    session_factory: SessionFactory,
    embedder: EmbedderDep,
    settings: SettingsDep,
    workspace: WorkspaceDep,
    approvals: ApprovalsDep,
) -> StreamingResponse:
    """Enregistre le message de l'utilisateur, puis streame et enregistre la réponse du modèle.

    Le serveur reconstitue lui-même l'historique depuis la base : le client n'envoie que
    le nouveau message. Dans un projet, le modèle reçoit une présentation du projet, et
    avec `agent` il peut se servir des outils qui lisent et modifient son dossier. Avec
    `use_documents`, les extraits de documents les plus proches de la question sont
    ajoutés au prompt (RAG) et renvoyés comme sources.
    """
    repository = ConversationRepository(session)
    conversation = await get_or_404(repository, conversation_id)
    provider = get_provider_or_404(registry, request.provider)

    history = [
        ChatMessage(role=m.role, content=m.content) for m in conversation.messages if m.content
    ]
    history.append(ChatMessage(role="user", content=request.content))

    project = await project_of(session, conversation, workspace)
    if request.agent and project is None:
        raise HTTPException(status_code=400, detail="Agent mode needs a conversation in a project")

    # Les consignes passent en message « système », en tête de l'historique : elles guident
    # la réponse sans apparaître dans la conversation affichée. Un seul message système,
    # car certains modèles ignorent ceux qui suivent le premier.
    system: list[str] = []
    if project is not None:
        system.append(build_project_context(*project, agent=request.agent))

    sources: list[Source] = []
    warning: str | None = None
    if request.use_documents:
        sources, warning = await find_sources(
            request.content, embedder, DocumentRepository(session), settings.rag_top_k
        )
    if sources:
        system.append(build_context(sources))
    if system:
        history.insert(0, ChatMessage(role="system", content="\n\n".join(system)))

    toolbox = (
        Toolbox(
            project[1],
            max_output_chars=settings.agent_max_output_chars,
            command_timeout=settings.agent_command_timeout,
        )
        if request.agent and project is not None
        else None
    )

    if conversation.title is None:
        conversation.title = make_title(request.content)
    await repository.add_message(conversation_id, role="user", content=request.content)
    await session.commit()

    async def event_stream() -> AsyncIterator[str]:
        result = StreamResult()
        try:
            if request.use_documents:
                # Les sources partent en premier : l'interface les affiche avant la réponse.
                yield sse(
                    "sources",
                    {"sources": [s.model_dump(mode="json") for s in sources], "warning": warning},
                )
            if toolbox is not None:
                answer = stream_agent(
                    provider,
                    request.model,
                    history,
                    result,
                    toolbox=toolbox,
                    approvals=approvals,
                    conversation_id=conversation_id,
                    max_steps=settings.agent_max_steps,
                )
            else:
                answer = stream_answer(provider, request.model, history, result)
            async for chunk in answer:
                yield chunk
        finally:
            # Même si le client coupe la connexion en pleine réponse (bouton stop, onglet
            # fermé), on enregistre ce qui a déjà été généré. Le « shield » protège cette
            # écriture de l'annulation que déclenche la déconnexion.
            with anyio.CancelScope(shield=True):
                await save_answer(session_factory, conversation_id, request, result, sources)

    return sse_response(event_stream())


@router.post("/{conversation_id}/approvals/{call_id}", status_code=status.HTTP_204_NO_CONTENT)
async def answer_approval(
    conversation_id: uuid.UUID, call_id: str, request: ApprovalRequest, approvals: ApprovalsDep
) -> None:
    """La réponse de l'utilisateur à une demande d'autorisation, attendue par le stream."""
    if not approvals.answer(conversation_id, call_id, request.decision):
        raise HTTPException(status_code=404, detail="No pending approval for this call")


async def save_answer(
    session_factory: SessionFactory,
    conversation_id: uuid.UUID,
    request: SendMessageRequest,
    result: StreamResult,
    sources: list[Source],
) -> None:
    # Une session neuve : celle de la requête a pu être fermée pendant le stream.
    try:
        async with session_factory() as session:
            await ConversationRepository(session).add_message(
                conversation_id,
                role="assistant",
                content=result.content,
                reasoning=result.reasoning or None,
                provider=request.provider,
                model=request.model,
                metrics=result.metrics,
                error=result.error,
                stopped=not result.finished and result.error is None,
                sources=[s.model_dump(mode="json") for s in sources] or None,
                steps=result.steps or None,
            )
            await session.commit()
    except SQLAlchemyError, OSError:
        # La réponse est déjà partie : impossible de prévenir le client, on journalise.
        logger.exception("Could not save the answer of conversation %s", conversation_id)
