"""Les tables de la base, décrites en Python avec l'ORM de SQLAlchemy."""

import uuid
from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, false
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Taille des vecteurs d'embeddings, celle de nomic-embed-text. Changer de modèle pour un
# modèle d'une autre taille demande une migration (la colonne est typée vector(768)).
EMBEDDING_DIMENSIONS = 768


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Classe mère des modèles : elle tient le catalogue des tables (`Base.metadata`)."""


class Project(Base):
    """Un dossier de code auquel on rattache des conversations, comme dans Claude Code."""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    name: Mapped[str] = mapped_column(String(200))
    # Relatif au dossier de travail (NETHERBRAIN_WORKSPACE_ROOT), avec des « / ». Unique :
    # un dossier n'appartient qu'à un seul projet.
    path: Mapped[str] = mapped_column(String(1024), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Conversation(Base):
    __tablename__ = "conversations"

    # UUID v7 : unique comme un UUID classique, mais ordonné par date de création.
    # Les index restent compacts et trier par identifiant revient à trier par date.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    title: Mapped[str | None] = mapped_column(String(200))
    # SET NULL : supprimer un projet garde ses conversations, qui redeviennent de simples
    # discussions. On ne détruit jamais plus que ce qui est demandé.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL", name="fk_conversations_project_id_projects"),
        index=True,
    )
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
    # Extraits de documents utilisés pour répondre (RAG), avec leur provenance.
    sources: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql")
    )
    # Outils utilisés par l'agent pour produire la réponse, dans l'ordre.
    steps: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages", lazy="raise")
    # Les fichiers envoyés avec ce message. viewonly : ils existent avant le message et lui
    # sont rattachés par une requête UPDATE, jamais en passant par cette relation.
    attachments: Mapped[list[Document]] = relationship(
        order_by="Document.id", lazy="raise", viewonly=True
    )


class Comparison(Base):
    """La même question posée à plusieurs modèles."""

    __tablename__ = "comparisons"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    prompt: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    results: Mapped[list[ComparisonResult]] = relationship(
        back_populates="comparison",
        order_by="ComparisonResult.position",
        lazy="raise",
        passive_deletes=True,
    )


class ComparisonResult(Base):
    """La réponse d'un des modèles d'une comparaison."""

    __tablename__ = "comparison_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    comparison_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("comparisons.id", ondelete="CASCADE"), index=True
    )
    # Ordre d'affichage des colonnes, celui choisi par l'utilisateur.
    position: Mapped[int]
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(200))
    # pending (pas encore lancée), running (en cours), puis done, error ou stopped.
    state: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    content: Mapped[str] = mapped_column(Text, default="", server_default="")
    reasoning: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql")
    )
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    comparison: Mapped[Comparison] = relationship(back_populates="results", lazy="raise")


class Document(Base):
    """Un fichier joint à une conversation : son texte, et ses morceaux pour la recherche."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    name: Mapped[str] = mapped_column(String(255))
    # Chemin dans le dossier joint (« app/src/main.py ») ; None pour un fichier joint seul.
    path: Mapped[str | None] = mapped_column(String(1024))
    # La conversation du fichier : la supprimer supprime aussi ses fichiers.
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "conversations.id",
            ondelete="CASCADE",
            name="fk_documents_conversation_id_conversations",
        ),
        index=True,
    )
    # Le message de l'utilisateur qui l'a envoyé ; None tant qu'il attend dans la zone de saisie.
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL", name="fk_documents_message_id_messages")
    )
    # Le texte extrait, envoyé en entier au modèle quand il est court. « deferred » : les
    # listes de fichiers ne le chargent pas, car il peut être très long.
    content: Mapped[str | None] = mapped_column(Text, deferred=True)
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int]
    # processing (indexation en cours), ready, ou error.
    status: Mapped[str] = mapped_column(
        String(16), default="processing", server_default="processing"
    )
    error: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class DocumentChunk(Base):
    """Un morceau de document et son vecteur : ce que retrouve la recherche."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        # Index HNSW (un graphe de voisins) : retrouve les vecteurs les plus proches sans
        # comparer la question à chaque morceau. vector_cosine_ops : distance cosinus.
        Index(
            "ix_document_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int]
    # Page d'origine (PDF), pour pouvoir la citer.
    page: Mapped[int | None]
    content: Mapped[str] = mapped_column(Text)
    # Type vector de pgvector sous PostgreSQL ; simple liste JSON sous SQLite (tests).
    embedding: Mapped[list[float]] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS).with_variant(JSON(), "sqlite")
    )
