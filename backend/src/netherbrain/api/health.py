from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Sonde de vivacité (liveness) : répond tant que le processus tourne."""
    return {"status": "ok"}
