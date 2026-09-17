"""Rattache les documents aux conversations : ils deviennent des fichiers joints au chat.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Les documents importés avant cette version n'ont pas de conversation : ils restent en
    # base, mais plus aucune page ne les affiche.
    with op.batch_alter_table("documents") as batch:
        batch.add_column(sa.Column("path", sa.String(length=1024), nullable=True))
        batch.add_column(sa.Column("conversation_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("message_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("content", sa.Text(), nullable=True))
        batch.create_foreign_key(
            "fk_documents_conversation_id_conversations",
            "conversations",
            ["conversation_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_foreign_key(
            "fk_documents_message_id_messages",
            "messages",
            ["message_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_documents_conversation_id", "documents", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_documents_conversation_id", table_name="documents")
    with op.batch_alter_table("documents") as batch:
        batch.drop_column("content")
        batch.drop_column("message_id")
        batch.drop_column("conversation_id")
        batch.drop_column("path")
