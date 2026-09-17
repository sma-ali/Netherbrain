"""Crée la table des projets et rattache les conversations à un projet.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("path"),
    )

    # SQLite ne sait pas ajouter une clé étrangère à une table existante. Le « mode batch »
    # d'Alembic contourne le problème en recréant la table (copie, suppression, renommage) ;
    # sous PostgreSQL, il se contente d'un ALTER TABLE classique.
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(sa.Column("project_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_conversations_project_id_projects",
            "projects",
            ["project_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_conversations_project_id", "conversations", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_conversations_project_id", table_name="conversations")
    # Supprimer la colonne supprime aussi la clé étrangère qui s'appuie dessus.
    with op.batch_alter_table("conversations") as batch:
        batch.drop_column("project_id")
    op.drop_table("projects")
