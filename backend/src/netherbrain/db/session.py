from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def create_engine(database_url: str) -> AsyncEngine:
    """Crée le moteur SQLAlchemy, c'est-à-dire le pool de connexions vers la base."""
    connect_args = {}
    if database_url.startswith("postgresql+asyncpg"):
        # Échouer vite si la base est injoignable, plutôt que de faire patienter la requête.
        connect_args["timeout"] = 5
    # pool_pre_ping : vérifie qu'une connexion du pool est encore vivante avant de s'en servir
    # (utile si la base a redémarré entre-temps).
    return create_async_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
