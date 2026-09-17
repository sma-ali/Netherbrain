"""Fiches des modèles : ce que chaque fournisseur sait dire de ses modèles, harmonisé."""

import re
from typing import Any

from netherbrain.schemas import ModelCard

# Ollama ne fournit pas de description : quelques notes par famille, repérée par le début
# du nom du modèle. La première correspondance l'emporte, d'où les plus précises en tête.
LOCAL_NOTES: list[tuple[str, str]] = [
    ("deepseek-r1", "DeepSeek's reasoning model (distilled): thinks at length before answering."),
    ("qwen3-coder", "Alibaba's Qwen, specialised in code."),
    ("qwen3-vl", "Alibaba's Qwen with vision: it can read images."),
    ("qwen", "Alibaba's all-rounder: strong at code and maths, optional reasoning."),
    ("gemma", "Google's open models: compact and multilingual."),
    ("gpt-oss", "OpenAI's open-weight model, with an adjustable reasoning effort."),
    ("llama", "Meta's widely used general-purpose models."),
    ("magistral", "Mistral AI's reasoning model."),
    ("devstral", "Mistral AI's model for coding agents."),
    ("mistral", "Mistral AI (France): efficient, good in French."),
    ("phi", "Microsoft's small models, strong at reasoning for their size."),
    ("granite", "IBM's models, geared towards business use and tools."),
    ("nemotron", "NVIDIA's models, tuned for reasoning and tool use."),
    ("glm", "Zhipu AI's models, strong at code and agents."),
]

EMBEDDING_NOTE = "Embedding model: turns text into vectors for search and RAG, not for chat."

# « 8.2B », « …-120b-a12b », « gpt-oss:20b » : un nombre suivi d'un b isolé.
_BILLIONS = re.compile(r"(\d+(?:\.\d+)?)b(?![a-z])", re.IGNORECASE)
_CODE_MARKERS = ("code", "coder", "codestral", "devstral")


def parse_billions(text: str | None) -> float | None:
    """Nombre de milliards de paramètres lu dans un texte, s'il y figure."""
    if not text:
        return None
    match = _BILLIONS.search(text)
    return float(match.group(1)) if match else None


def looks_like_code_model(model_id: str) -> bool:
    return any(marker in model_id.lower() for marker in _CODE_MARKERS)


def local_note(model_id: str) -> str | None:
    name = model_id.lower()
    return next((note for prefix, note in LOCAL_NOTES if name.startswith(prefix)), None)


def card_from_ollama(provider: str, raw: dict[str, Any]) -> ModelCard:
    """Fiche d'un modèle à partir de l'API native d'Ollama (GET /api/tags)."""
    details = raw.get("details") or {}
    reported = set(raw.get("capabilities") or [])
    model_id = raw.get("name") or raw.get("model") or ""

    # Ollama parle de « thinking » ; on harmonise avec les autres fournisseurs.
    capabilities = [
        label
        for flag, label in (
            ("thinking", "reasoning"),
            ("tools", "tools"),
            ("vision", "vision"),
            ("embedding", "embedding"),
        )
        if flag in reported
    ]
    if looks_like_code_model(model_id):
        capabilities.append("code")

    return ModelCard(
        id=model_id,
        provider=provider,
        local=True,
        name=model_id,
        description=EMBEDDING_NOTE if "embedding" in reported else local_note(model_id),
        family=details.get("family"),
        parameters_b=parse_billions(details.get("parameter_size")),
        quantization=details.get("quantization_level"),
        size_bytes=raw.get("size"),
        context_length=details.get("context_length"),
        capabilities=capabilities,
        free=True,
    )


def card_from_openai_compatible(
    provider: str, model_id: str, extra: dict[str, Any], local: bool = False
) -> ModelCard:
    """Fiche d'un modèle à partir de GET /models d'une API compatible OpenAI.

    Le format standard ne donne presque que l'identifiant. OpenRouter et Groq y ajoutent
    des champs (nom, description, contexte, capacités, prix) qu'on récupère s'ils existent.
    """
    architecture = extra.get("architecture") or {}
    parameters = set(extra.get("supported_parameters") or [])
    inputs = set(architecture.get("input_modalities") or [])

    capabilities = []
    if parameters & {"reasoning", "include_reasoning"}:
        capabilities.append("reasoning")
    if "tools" in parameters:
        capabilities.append("tools")
    if "image" in inputs:
        capabilities.append("vision")
    if looks_like_code_model(model_id):
        capabilities.append("code")

    return ModelCard(
        id=model_id,
        provider=provider,
        local=local,
        name=extra.get("name") or model_id,
        description=extra.get("description") or (local_note(model_id) if local else None),
        parameters_b=parse_billions(model_id),
        # OpenRouter dit « context_length », Groq « context_window ».
        context_length=extra.get("context_length") or extra.get("context_window"),
        capabilities=capabilities,
        free=is_free(model_id, extra.get("pricing")),
    )


def is_free(model_id: str, pricing: dict[str, Any] | None) -> bool | None:
    """Gratuit, payant, ou inconnu (None) quand le fournisseur ne publie pas ses prix."""
    if model_id.endswith(":free"):
        return True
    if not pricing:
        return None
    try:
        return all(float(price) == 0 for price in pricing.values())
    except TypeError, ValueError:
        return None
