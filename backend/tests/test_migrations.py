"""Les migrations Alembic et les modèles SQLAlchemy doivent décrire le même schéma.

Sinon, les tests (qui créent les tables depuis les modèles) passeraient alors que
la vraie base (créée par les migrations) serait différente.
"""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from netherbrain.db.migrate import alembic_config
from netherbrain.db.models import Base


def test_migrations_create_the_schema_described_by_the_models(tmp_path):
    database = tmp_path / "migrations.db"
    command.upgrade(alembic_config(f"sqlite+aiosqlite:///{database}"), "head")

    with create_engine(f"sqlite:///{database}").connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)

    assert differences == []


def test_migrations_can_be_rolled_back(tmp_path):
    database = tmp_path / "migrations.db"
    config = alembic_config(f"sqlite+aiosqlite:///{database}")

    command.upgrade(config, "head")
    command.downgrade(config, "base")

    with create_engine(f"sqlite:///{database}").connect() as connection:
        assert inspect(connection).get_table_names() == ["alembic_version"]
