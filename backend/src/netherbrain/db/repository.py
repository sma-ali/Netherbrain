"""Accès aux conversations en base : toutes les requêtes SQL passent par ici."""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from netherbrain.db.models import Conversation, Message, utcnow


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

    async def create(self, title: str | None = None) -> Conversation:
        conversation = Conversation(title=title)
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


def make_title(content: str, max_length: int = 60) -> str:
    """Titre d'une conversation : le début du premier message, coupé proprement sur un mot."""
    text = " ".join(content.split())
    if len(text) <= max_length:
        return text
    return text[:max_length].rsplit(" ", 1)[0] + "…"
