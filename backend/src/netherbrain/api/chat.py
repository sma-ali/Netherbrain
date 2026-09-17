from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from netherbrain.api.deps import Registry, get_provider_or_404
from netherbrain.api.streaming import StreamResult, sse_response, stream_answer
from netherbrain.providers import ProviderResult
from netherbrain.schemas import ChatRequest, ModelInfo, ModelsResponse, ProviderStatus

router = APIRouter(prefix="/api", tags=["chat"])


def provider_statuses(results: list[ProviderResult[Any]]) -> list[ProviderStatus]:
    return [
        ProviderStatus(name=r.name, local=r.local, available=r.error is None, error=r.error)
        for r in results
    ]


@router.get("/models")
async def list_models(registry: Registry) -> ModelsResponse:
    """Les modèles de tous les fournisseurs, plus l'état de chacun.

    Répond toujours 200 : un fournisseur injoignable apparaît comme indisponible
    au lieu de faire échouer toute la requête. Les fiches complètes servent ici
    à savoir quels modèles savent appeler des outils (mode agent) et lire des images.
    """
    results = await registry.describe_all()
    return ModelsResponse(
        models=[
            ModelInfo(
                id=card.id,
                provider=result.name,
                tools="tools" in card.capabilities,
                vision="vision" in card.capabilities,
            )
            for result in results
            for card in result.items
            # Les modèles d'embeddings ne savent pas discuter.
            if "embedding" not in card.capabilities
        ],
        providers=provider_statuses(results),
    )


@router.post("/chat")
async def chat(request: ChatRequest, registry: Registry) -> StreamingResponse:
    """Streame une réponse sans rien enregistrer : le client envoie toute la conversation.

    Sert quand l'historique est indisponible, et pour les appels ponctuels (curl, scripts).
    """
    provider = get_provider_or_404(registry, request.provider)
    return sse_response(stream_answer(provider, request.model, request.messages, StreamResult()))
