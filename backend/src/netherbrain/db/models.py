"""Les tables de la base, décrites en Python avec l'ORM de SQLAlchemy."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, false
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Classe mère des modèles : elle tient le catalogue des tables (`Base.metadata`)."""


class Conversation(Base):
    __tablename__ = "conversations"

    # UUID v7 : unique comme un UUID classique, mais ordonné par date de création.
    # Les index restent compacts et trier par identifiant revient à trier par date.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    title: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    # lazy="raise" : accéder aux messages sans les avoir chargés explicitement lève une
    # erreur, au lieu de lancer une requête en douce (impossible en asynchrone, de toute façon).
    # passive_deletes : la base supprime elle-même les messages (ON DELETE CASCADE).
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        order_by="Message.id",
        lazy="raise",
        passive_deletes=True,
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    reasoning: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(200))
    # JSONB sous PostgreSQL (format binaire, interrogeable), JSON générique ailleurs (SQLite).
    metrics: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql")
    )
    error: Mapped[str | None] = mapped_column(Text)
    stopped: Mapped[bool] = mapped_column(default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages", lazy="raise")
