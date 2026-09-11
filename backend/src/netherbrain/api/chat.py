from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from netherbrain.api.deps import Registry, get_provider_or_404
from netherbrain.api.streaming import StreamResult, sse_response, stream_answer
from netherbrain.schemas import ChatRequest, ModelInfo, ModelsResponse, ProviderStatus

router = APIRouter(prefix="/api", tags=["chat"])


@router.get("/models")
async def list_models(registry: Registry) -> ModelsResponse:
    """Les modèles de tous les fournisseurs, plus l'état de chacun.

    Répond toujours 200 : un fournisseur injoignable apparaît comme indisponible
    au lieu de faire échouer toute la requête.
    """
    results = await registry.list_all()
    return ModelsResponse(
        models=[ModelInfo(id=model, provider=r.name) for r in results for model in r.models],
        providers=[
            ProviderStatus(name=r.name, available=r.error is None, error=r.error) for r in results
        ],
    )


@router.post("/chat")
async def chat(request: ChatRequest, registry: Registry) -> StreamingResponse:
    """Streame une réponse sans rien enregistrer : le client envoie toute la conversation.

    Sert quand l'historique est indisponible, et pour les appels ponctuels (curl, scripts).
    """
    provider = get_provider_or_404(registry, request.provider)
    return sse_response(stream_answer(provider, request.model, request.messages, StreamResult()))
