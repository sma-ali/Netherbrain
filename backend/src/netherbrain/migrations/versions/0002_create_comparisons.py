"""Crée les tables des comparaisons et de leurs réponses.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Identifiants de révision, utilisés par Alembic pour ordonner les migrations.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "comparisons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_comparisons_created_at", "comparisons", ["created_at"])

    op.create_table(
        "comparison_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("comparison_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("state", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column(
            "metrics", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["comparison_id"], ["comparisons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_comparison_results_comparison_id", "comparison_results", ["comparison_id"])


def downgrade() -> None:
    op.drop_index("ix_comparison_results_comparison_id", table_name="comparison_results")
    op.drop_table("comparison_results")
    op.drop_index("ix_comparisons_created_at", table_name="comparisons")
    op.drop_table("comparisons")
