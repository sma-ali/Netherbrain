"""Contrats de données partagés par la couche API et les fournisseurs."""

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    messages: list[ChatMessage] = Field(min_length=1)


class ModelInfo(BaseModel):
    id: str
    provider: str


class ProviderStatus(BaseModel):
    name: str
    available: bool
    error: str | None = None


class ModelsResponse(BaseModel):
    models: list[ModelInfo]
    providers: list[ProviderStatus]


# --- Événements émis par un fournisseur pendant qu'il streame une réponse ---


class TokenEvent(BaseModel):
    """Un morceau de la réponse finale."""

    type: Literal["token"] = "token"
    content: str


class ReasoningEvent(BaseModel):
    """Un morceau de la « réflexion » du modèle.

    Concerne les modèles de raisonnement, comme Qwen3 ou DeepSeek-R1.
    """

    type: Literal["reasoning"] = "reasoning"
    content: str


class UsageEvent(BaseModel):
    """Décompte des tokens, envoyé une seule fois à la fin du stream."""

    type: Literal["usage"] = "usage"
    prompt_tokens: int
    completion_tokens: int


StreamEvent = TokenEvent | ReasoningEvent | UsageEvent
