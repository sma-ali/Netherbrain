"""llama.cpp : un serveur local lancé à la main (`llama-server`), compatible avec l'API d'OpenAI.

Il sert les modèles qu'Ollama ne sait pas lire, comme les GGUF ternaires. Son `/v1/models` ne
donne presque rien : les détails (fenêtre de contexte, vision, outils) se lisent dans `/props`,
un point d'entrée propre à llama.cpp.
"""

from pathlib import Path
from typing import Any

import httpx

from netherbrain.providers.catalog import parse_billions
from netherbrain.providers.openai_compatible import OpenAICompatibleProvider
from netherbrain.schemas import ModelCard


class LlamaCppProvider(OpenAICompatibleProvider):
    def __init__(
        self,
        base_url: str,
        name: str = "llamacpp",
        *,
        timeout: float = 600.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        # local : le modèle tourne sur cette machine, et partage donc le GPU.
        super().__init__(name, base_url, timeout=timeout, local=True)
        # http://localhost:8080/v1 → http://localhost:8080
        self._native_url = base_url.rstrip("/").removesuffix("/v1")
        self._transport = transport

    async def describe_models(self) -> list[ModelCard]:
        cards = await super().describe_models()
        properties = await read_properties(self._native_url, transport=self._transport)
        return [describe_with_properties(card, properties) for card in cards]


async def read_properties(
    native_url: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> dict[str, Any]:
    """Ce que le serveur dit du modèle chargé ; vide s'il ne répond pas."""
    try:
        async with httpx.AsyncClient(timeout=5, transport=transport) as client:
            response = await client.get(f"{native_url}/props")
            response.raise_for_status()
            properties = response.json()
    except httpx.HTTPError, ValueError:
        return {}
    return properties if isinstance(properties, dict) else {}


def describe_with_properties(card: ModelCard, properties: dict[str, Any]) -> ModelCard:
    """Complète la fiche d'un modèle avec ce que `/props` révèle du serveur."""
    generation = properties.get("default_generation_settings") or {}
    modalities = properties.get("modalities") or {}
    template = properties.get("chat_template") or ""
    # Le serveur ne liste pas les capacités : elles se déduisent du gabarit de discussion, qui
    # décrit comment écrire un appel d'outil ou une réflexion, et des entrées acceptées.
    capabilities = set(card.capabilities)
    if "tools" in template:
        capabilities.add("tools")
    if "think" in template.lower():
        capabilities.add("reasoning")
    if modalities.get("vision"):
        capabilities.add("vision")

    name = Path(str(properties.get("model_path") or "")).stem or card.name
    return card.model_copy(
        update={
            "name": name,
            "description": card.description or "Served by llama.cpp on this machine.",
            "parameters_b": card.parameters_b or parse_billions(name),
            "context_length": card.context_length or generation.get("n_ctx"),
            "capabilities": sorted(capabilities),
        }
    )
