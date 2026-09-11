import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from netherbrain.api import chat, conversations, health
from netherbrain.api.deps import get_engine
from netherbrain.config import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    # À l'arrêt : fermer proprement les connexions à la base, si elles ont été ouvertes.
    if get_engine.cache_info().currsize:
        await get_engine().dispose()


async def database_unavailable(request: Request, exc: Exception) -> JSONResponse:
    """Base injoignable ou en erreur : un 503 explicite plutôt qu'une erreur 500 opaque."""
    logger.warning("Database error on %s: %s", request.url.path, exc)
    return JSONResponse(status_code=503, content={"detail": "Database unavailable"})


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(title="Netherbrain API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # asyncpg lève des OSError (connexion refusée, hôte inconnu, délai dépassé)
    # que SQLAlchemy n'enveloppe pas toujours dans ses propres exceptions.
    app.add_exception_handler(SQLAlchemyError, database_unavailable)
    app.add_exception_handler(OSError, database_unavailable)

    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(conversations.router)
    return app


app = create_app()
