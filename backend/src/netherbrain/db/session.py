from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def create_engine(database_url: str) -> AsyncEngine:
    """Crée le moteur SQLAlchemy, c'est-à-dire le pool de connexions vers la base."""
    connect_args = {}
    if database_url.startswith("postgresql+asyncpg"):
        # Échouer vite si la base est injoignable, plutôt que de faire patienter la requête.
        connect_args["timeout"] = 5
    # pool_pre_ping : vérifie qu'une connexion du pool est encore vivante avant de s'en servir
    # (utile si la base a redémarré entre-temps).
    engine = create_async_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
    enable_pgvector(engine)
    return engine


def enable_pgvector(engine: AsyncEngine) -> None:
    """Apprend à asyncpg à faire circuler le type `vector` de pgvector (PostgreSQL seulement).

    Le type `Vector` de SQLAlchemy convertit déjà les listes en texte « [0.1,0.2,…] » (et
    inversement) : asyncpg doit donc transmettre ce texte tel quel. Un codec binaire
    (pgvector.asyncpg.register_vector) ferait une seconde conversion, incompatible.
    """
    if engine.dialect.name != "postgresql":
        return

    @event.listens_for(engine.sync_engine, "connect")
    def register(dbapi_connection, _record) -> None:
        try:
            dbapi_connection.run_async(
                lambda connection: connection.set_type_codec(
                    "vector", schema="public", encoder=str, decoder=str, format="text"
                )
            )
        except ValueError:
            # Base neuve, extension pas encore installée par les migrations : rien à faire.
            pass
