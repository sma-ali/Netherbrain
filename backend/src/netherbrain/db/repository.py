"""Accès aux conversations en base : toutes les requêtes SQL passent par ici."""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, delete, func, select, union_all, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from netherbrain.db.models import (
    Comparison,
    ComparisonResult,
    Conversation,
    Document,
    DocumentChunk,
    Message,
    Project,
    utcnow,
)
from netherbrain.rag.chunking import Chunk
from netherbrain.rag.embeddings import cosine_similarity
from netherbrain.schemas import ModelStats, Source


class ConversationRepository:
    """Les opérations sur les conversations, sans jamais valider la transaction.

    C'est l'appelant (la route) qui décide quand faire `commit()` : plusieurs opérations
    peuvent ainsi former une seule transaction, appliquée entièrement ou pas du tout.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_recent(self, limit: int = 100) -> Sequence[Conversation]:
        result = await self._session.scalars(
            select(Conversation).order_by(Conversation.updated_at.desc()).limit(limit)
        )
        return result.all()

    async def get(self, conversation_id: uuid.UUID) -> Conversation | None:
        # selectinload charge tous les messages en une seule requête supplémentaire,
        # au lieu d'une requête par message (le fameux problème « N+1 »).
        return await self._session.scalar(
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .options(selectinload(Conversation.messages))
        )

    async def create(
        self, title: str | None = None, project_id: uuid.UUID | None = None
    ) -> Conversation:
        conversation = Conversation(title=title, project_id=project_id)
        self._session.add(conversation)
        await self._session.flush()
        return conversation

    async def delete(self, conversation_id: uuid.UUID) -> bool:
        """Supprime une conversation ; la base supprime ses messages (ON DELETE CASCADE)."""
        result = await self._session.execute(
            delete(Conversation).where(Conversation.id == conversation_id)
        )
        return result.rowcount > 0

    async def add_message(self, conversation_id: uuid.UUID, **fields: Any) -> Message:
        message = Message(conversation_id=conversation_id, **fields)
        self._session.add(message)
        # La conversation remonte en tête de la liste.
        await self._session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(updated_at=utcnow())
        )
        await self._session.flush()
        return message


class ProjectRepository:
    """Les projets ; comme ailleurs, sans commit()."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> Sequence[Project]:
        # lower() : un tri alphabétique qui ignore les majuscules.
        result = await self._session.scalars(select(Project).order_by(func.lower(Project.name)))
        return result.all()

    async def get(self, project_id: uuid.UUID) -> Project | None:
        return await self._session.get(Project, project_id)

    async def get_by_path(self, path: str) -> Project | None:
        return await self._session.scalar(select(Project).where(Project.path == path))

    async def create(self, name: str, path: str) -> Project:
        project = Project(name=name, path=path)
        self._session.add(project)
        await self._session.flush()
        return project

    async def delete(self, project_id: uuid.UUID) -> bool:
        """Supprime le projet ; la base détache ses conversations (ON DELETE SET NULL)."""
        result = await self._session.execute(delete(Project).where(Project.id == project_id))
        return result.rowcount > 0


def make_title(content: str, max_length: int = 60) -> str:
    """Titre d'une conversation : le début du premier message, coupé proprement sur un mot."""
    text = " ".join(content.split())
    if len(text) <= max_length:
        return text
    return text[:max_length].rsplit(" ", 1)[0] + "…"


class ComparisonRepository:
    """Les opérations sur les comparaisons ; comme pour les conversations, sans commit()."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_recent(self, limit: int = 100) -> Sequence[Comparison]:
        result = await self._session.scalars(
            select(Comparison)
            .order_by(Comparison.created_at.desc())
            .limit(limit)
            .options(selectinload(Comparison.results))
        )
        return result.all()

    async def get(self, comparison_id: uuid.UUID) -> Comparison | None:
        return await self._session.scalar(
            select(Comparison)
            .where(Comparison.id == comparison_id)
            .options(selectinload(Comparison.results))
        )

    async def create(self, prompt: str, contenders: list[tuple[str, str]]) -> Comparison:
        """Crée la comparaison et, pour chaque (fournisseur, modèle), une réponse en attente."""
        comparison = Comparison(
            prompt=prompt,
            results=[
                ComparisonResult(position=position, provider=provider, model=model)
                for position, (provider, model) in enumerate(contenders)
            ],
        )
        self._session.add(comparison)
        await self._session.flush()
        return comparison

    async def delete(self, comparison_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(Comparison).where(Comparison.id == comparison_id)
        )
        return result.rowcount > 0

    async def get_result(
        self, comparison_id: uuid.UUID, result_id: uuid.UUID
    ) -> tuple[ComparisonResult, str] | None:
        """Une réponse de la comparaison, avec la question posée."""
        row = (
            await self._session.execute(
                select(ComparisonResult, Comparison.prompt)
                .join(Comparison)
                .where(
                    ComparisonResult.id == result_id,
                    ComparisonResult.comparison_id == comparison_id,
                )
            )
        ).first()
        return (row[0], row[1]) if row else None

    async def save_result(self, result_id: uuid.UUID, **fields: Any) -> None:
        await self._session.execute(
            update(ComparisonResult).where(ComparisonResult.id == result_id).values(**fields)
        )


class DocumentRepository:
    """Les documents importés et leurs morceaux ; comme ailleurs, sans commit()."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_recent(self) -> Sequence[Document]:
        result = await self._session.scalars(select(Document).order_by(Document.created_at.desc()))
        return result.all()

    async def create(self, name: str, content_type: str, size_bytes: int) -> Document:
        document = Document(name=name, content_type=content_type, size_bytes=size_bytes)
        self._session.add(document)
        await self._session.flush()
        return document

    async def delete(self, document_id: uuid.UUID) -> bool:
        """Supprime un document ; la base supprime ses morceaux (ON DELETE CASCADE)."""
        result = await self._session.execute(delete(Document).where(Document.id == document_id))
        return result.rowcount > 0

    async def mark(self, document_id: uuid.UUID, **fields: Any) -> None:
        await self._session.execute(
            update(Document).where(Document.id == document_id).values(**fields)
        )

    async def add_chunks(
        self, document_id: uuid.UUID, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> None:
        self._session.add_all(
            DocumentChunk(
                document_id=document_id,
                position=position,
                page=chunk.page,
                content=chunk.content,
                embedding=embedding,
            )
            for position, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True))
        )
        await self._session.flush()

    async def search(self, embedding: list[float], limit: int) -> list[Source]:
        """Les morceaux dont le sens est le plus proche de la question (documents prêts)."""
        ready_chunks = (
            select(
                DocumentChunk.document_id, Document.name, DocumentChunk.page, DocumentChunk.content
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.status == "ready")
        )
        connection = await self._session.connection()

        if connection.dialect.name == "postgresql":
            # pgvector : distance cosinus (opérateur <=>), accélérée par l'index HNSW.
            distance = DocumentChunk.embedding.cosine_distance(embedding)
            rows = await self._session.execute(
                ready_chunks.add_columns(1 - distance).order_by(distance).limit(limit)
            )
            return [_source(*row) for row in rows]

        # Sans pgvector (SQLite des tests), on compare en Python. Le résultat est le même,
        # mais on lit tous les morceaux, là où l'index de PostgreSQL n'en visite qu'une partie.
        rows = await self._session.execute(ready_chunks.add_columns(DocumentChunk.embedding))
        scored = [(*row[:4], cosine_similarity(embedding, row[4])) for row in rows]
        scored.sort(key=lambda row: row[4], reverse=True)
        return [_source(*row) for row in scored[:limit]]


def _source(
    document_id: uuid.UUID, document_name: str, page: int | None, content: str, score: float
) -> Source:
    return Source(
        document_id=document_id,
        document_name=document_name,
        page=page,
        content=content,
        score=round(float(score), 3),
    )


def _measures(table: type[Message] | type[ComparisonResult]) -> Select:
    """Fournisseur, modèle et métriques de chaque réponse enregistrée dans `table`."""
    return select(
        table.provider.label("provider"),
        table.model.label("model"),
        # as_float() lit un champ du JSON : `->>` sous PostgreSQL, json_extract sous SQLite.
        table.metrics["total_ms"].as_float().label("total_ms"),
        table.metrics["ttft_ms"].as_float().label("ttft_ms"),
        table.metrics["tokens_per_second"].as_float().label("tokens_per_second"),
    )


async def model_stats(session: AsyncSession) -> dict[tuple[str, str], ModelStats]:
    """Moyennes mesurées par modèle, sur toutes les réponses : chat et comparaisons."""
    answers = union_all(
        _measures(Message).where(Message.role == "assistant"),
        _measures(ComparisonResult),
    ).subquery()
    # Une réponse « terminée » a une durée totale ; les réponses en erreur n'en ont pas.
    completed = func.count(answers.c.total_ms)
    rows = await session.execute(
        select(
            answers.c.provider,
            answers.c.model,
            completed,
            func.avg(answers.c.ttft_ms),
            func.avg(answers.c.tokens_per_second),
        )
        .where(answers.c.provider.is_not(None))
        .group_by(answers.c.provider, answers.c.model)
        .having(completed > 0)
    )
    return {
        (provider, model): ModelStats(
            answers=count,
            avg_ttft_ms=round(ttft) if ttft is not None else None,
            avg_tokens_per_second=round(tps, 1) if tps is not None else None,
        )
        for provider, model, count, ttft, tps in rows
    }
