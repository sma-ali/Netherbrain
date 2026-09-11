"""Contrats de données partagés par la couche API et les fournisseurs."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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
    # Modèles exécutés sur cette machine : ils se partagent le GPU.
    local: bool = False
    available: bool
    error: str | None = None


class ModelsResponse(BaseModel):
    models: list[ModelInfo]
    providers: list[ProviderStatus]


# --- Conversations enregistrées ---


class ConversationSummary(BaseModel):
    # from_attributes : ces schémas se construisent directement depuis les objets de l'ORM.
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class StoredMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    reasoning: str | None = None
    provider: str | None = None
    model: str | None = None
    metrics: dict[str, Any] | None = None
    error: str | None = None
    stopped: bool = False
    created_at: datetime


class ConversationDetail(ConversationSummary):
    messages: list[StoredMessage]


class SendMessageRequest(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    content: str = Field(min_length=1)


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
