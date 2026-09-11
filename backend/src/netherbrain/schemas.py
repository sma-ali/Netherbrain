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


# --- Catalogue des modèles ---


class ModelStats(BaseModel):
    """Ce que Netherbrain a mesuré en utilisant un modèle sur cette installation."""

    answers: int
    avg_ttft_ms: float | None = None
    avg_tokens_per_second: float | None = None


class ModelCard(BaseModel):
    """La fiche d'un modèle dans le catalogue."""

    id: str
    provider: str
    local: bool = False
    name: str
    description: str | None = None
    family: str | None = None
    # Milliards de paramètres, quand on les connaît : la « taille » du modèle.
    parameters_b: float | None = None
    quantization: str | None = None
    size_bytes: int | None = None
    context_length: int | None = None
    # Parmi : reasoning, tools, vision, code, embedding.
    capabilities: list[str] = Field(default_factory=list)
    free: bool | None = None
    stats: ModelStats | None = None


class CatalogResponse(BaseModel):
    models: list[ModelCard]
    providers: list[ProviderStatus]
    # False si la base est indisponible : les fiches s'affichent quand même, sans les mesures.
    stats_available: bool = True


# --- Conversations enregistrées ---


class ConversationSummary(BaseModel):
    # from_attributes : ces schémas se construisent directement depuis les objets de l'ORM.
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class Source(BaseModel):
    """Un extrait de document retrouvé pour répondre (RAG)."""

    document_id: uuid.UUID
    document_name: str
    page: int | None = None
    content: str
    # Similarité cosinus avec la question : proche de 1 = même sens.
    score: float


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
    sources: list[Source] | None = None
    created_at: datetime


class ConversationDetail(ConversationSummary):
    messages: list[StoredMessage]


class SendMessageRequest(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    content: str = Field(min_length=1)
    # Chercher dans les documents importés et s'appuyer sur eux pour répondre (RAG).
    use_documents: bool = False


# --- Documents (RAG) ---


class DocumentInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    content_type: str
    size_bytes: int
    # processing : indexation en cours ; ready : utilisable ; error : voir `error`.
    status: Literal["processing", "ready", "error"]
    error: str | None = None
    chunk_count: int
    created_at: datetime


# --- Comparaisons enregistrées ---

# pending : pas encore lancée ; running : en cours ; puis done, error ou stopped.
ResultState = Literal["pending", "running", "done", "error", "stopped"]


class Contender(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)


class CreateComparisonRequest(BaseModel):
    prompt: str = Field(min_length=1)
    contenders: list[Contender] = Field(min_length=2, max_length=4)


class ComparisonResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    provider: str
    model: str
    state: ResultState
    content: str
    reasoning: str | None = None
    metrics: dict[str, Any] | None = None
    error: str | None = None


class ComparisonSummary(BaseModel):
    id: uuid.UUID
    prompt: str
    created_at: datetime
    models: list[str]


class ComparisonDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prompt: str
    created_at: datetime
    results: list[ComparisonResultOut]


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
