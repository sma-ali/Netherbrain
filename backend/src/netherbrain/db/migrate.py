"""Applique les migrations de la base de données : `python -m netherbrain.db.migrate`.

Lancé au démarrage du conteneur, avant l'API. Contrairement à la commande `alembic`,
ce module n'a pas besoin du fichier alembic.ini : il trouve les migrations dans le
paquet installé.
"""

import logging
from importlib.resources import files

from alembic import command
from alembic.config import Config


def alembic_config(database_url: str | None = None) -> Config:
    config = Config()
    config.set_main_option("script_location", str(files("netherbrain") / "migrations"))
    if database_url:
        # La configuration d'Alembic interprète les « % » : un mot de passe encodé
        # dans l'URL (%40 pour @, par exemple) doit être échappé.
        config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def upgrade(database_url: str | None = None) -> None:
    """Amène la base à la dernière version du schéma (« head »)."""
    command.upgrade(alembic_config(database_url), "head")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    upgrade()
