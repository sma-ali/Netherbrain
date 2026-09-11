"""Point d'entrée d'Alembic : applique les migrations sur la base configurée."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from netherbrain.config import get_settings
from netherbrain.db.models import Base

config = context.config

# Lancé via alembic.ini (ligne de commande) : on applique sa configuration des logs.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Les modèles : Alembic les compare à la base pour générer les migrations (--autogenerate).
target_metadata = Base.metadata


def database_url() -> str:
    # Une URL passée explicitement (par les tests) a priorité sur la configuration de l'app.
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    """Mode hors ligne : écrit le SQL sans se connecter (`alembic upgrade head --sql`)."""
    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(database_url())
    async with engine.connect() as connection:
        # Alembic est synchrone : run_sync lui prête la connexion asynchrone.
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
