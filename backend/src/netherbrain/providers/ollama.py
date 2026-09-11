import httpx

from netherbrain.providers.base import ProviderError
from netherbrain.providers.catalog import card_from_ollama
from netherbrain.providers.openai_compatible import OpenAICompatibleProvider
from netherbrain.schemas import ModelCard


class OllamaProvider(OpenAICompatibleProvider):
    """Ollama : l'API compatible OpenAI pour discuter, l'API native pour décrire les modèles.

    La liste au format OpenAI ne contient que les identifiants ; l'API native d'Ollama
    donne en plus la taille, la quantification, le contexte et les capacités.
    """

    def __init__(
        self,
        base_url: str,
        name: str = "ollama",
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(name, base_url, local=True)
        # http://localhost:11434/v1 → http://localhost:11434
        self._native_url = base_url.rstrip("/").removesuffix("/v1")
        # Les tests remplacent le réseau par une réponse préparée à l'avance.
        self._transport = transport

    async def describe_models(self) -> list[ModelCard]:
        try:
            async with httpx.AsyncClient(timeout=10, transport=self._transport) as client:
                response = await client.get(f"{self._native_url}/api/tags")
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name}: {str(exc) or type(exc).__name__}") from exc
        cards = [card_from_ollama(self.name, raw) for raw in response.json().get("models", [])]
        return sorted(cards, key=lambda card: card.id)

    async def list_models(self) -> list[str]:
        # Les modèles d'embeddings ne savent pas discuter : on ne les propose pas au chat.
        cards = await self.describe_models()
        return [card.id for card in cards if "embedding" not in card.capabilities]
