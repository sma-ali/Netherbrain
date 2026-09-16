"""Garde les octets des images jointes au chat, pour les envoyer aux modèles qui les lisent.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # bytea sous PostgreSQL : jusqu'à 1 Go par valeur, bien au-delà de la taille d'import permise.
    with op.batch_alter_table("documents") as batch:
        batch.add_column(sa.Column("data", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.drop_column("data")
