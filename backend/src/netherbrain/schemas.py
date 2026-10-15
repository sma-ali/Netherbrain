"""Contrats de données partagés par la couche API et les fournisseurs."""

import uuid
from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ImageInput(BaseModel):
    """Une image envoyée au modèle."""

    # image/png, image/jpeg, image/webp ou image/gif.
    media_type: str
    # Les octets de l'image, encodés en base64 : c'est ainsi qu'elle voyage dans du JSON.
    data: str


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    # Les images jointes par l'utilisateur, pour les modèles qui savent les lire.
    images: list[ImageInput] | None = None
    # Les outils demandés par le modèle (role="assistant"), au format d'OpenAI.
    tool_calls: list[dict[str, Any]] | None = None
    # La réponse à un appel d'outil (role="tool") : l'identifiant de l'appel concerné.
    tool_call_id: str | None = None


class ChatRequest(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    messages: list[ChatMessage] = Field(min_length=1)


class ModelInfo(BaseModel):
    id: str
    provider: str
    # Sait appeler des outils : sans ça, pas de mode agent.
    tools: bool = False
    # Sait lire des images : sans ça, impossible de lui en envoyer.
    vision: bool = False


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


# --- Conseiller de modèles ---

# code : programmation ; reasoning : maths, logique ; writing : rédaction ; summary : longs
# documents ; chat : assistant généraliste ; vision : images ; agent : agit avec des outils ;
# multilingual : répond dans une autre langue que l'anglais.
Task = Literal["code", "reasoning", "writing", "summary", "chat", "vision", "agent", "multilingual"]
Requirement = Literal["vision", "tools", "long_context"]


class Needs(BaseModel):
    """Ce que la demande de l'utilisateur exige d'un modèle."""

    tasks: list[Task] = Field(min_length=1, max_length=3)
    requires: list[Requirement] = Field(default_factory=list)
    priority: Literal["quality", "balanced", "speed"] = "balanced"
    local_only: bool = False

    @field_validator("tasks", "requires", mode="before")
    @classmethod
    def without_duplicates(cls, value: Any) -> Any:
        # Un LLM répète parfois une tâche : on dédoublonne, et on garde les trois premières.
        return list(dict.fromkeys(value))[:3] if isinstance(value, list) else value

    @model_validator(mode="after")
    def implied_requirements(self) -> Self:
        # Certaines tâches supposent une capacité, qu'un LLM oublie parfois d'exiger : le code
        # la rajoute, pour ne jamais proposer un modèle incapable de faire la tâche.
        for task, requirement in (("vision", "vision"), ("agent", "tools")):
            if task in self.tasks and requirement not in self.requires:
                self.requires.append(requirement)
        return self


class RecommendRequest(BaseModel):
    query: str = Field(min_length=3, max_length=1000)
    # False : lecture par mots-clés, instantanée. L'interface s'en sert pour afficher un premier
    # podium tout de suite, avant la lecture par un LLM, plus fine mais plus lente.
    understand: bool = True


class ModelPick(BaseModel):
    """Un modèle recommandé, et ce qui justifie ce choix."""

    # best : le meilleur choix ; fastest : presque aussi bon, mais plus rapide ;
    # download : meilleur que ce qui est installé ; cloud : une alternative distante.
    role: Literal["best", "fastest", "download", "cloud"]
    # None pour un modèle pas encore installé.
    provider: str | None = None
    model: str
    local: bool
    # Utilisable tout de suite : installé, ou chez un fournisseur distant disponible.
    ready: bool
    score: float
    reasons: list[str]
    warnings: list[str] = Field(default_factory=list)
    pull_command: str | None = None
    # Le modèle retrouvé dans les benchmarks en ligne, s'il y en a un.
    benchmark: str | None = None


class BenchmarksStatus(BaseModel):
    source: str
    url: str
    # False sans clé d'API : le conseiller n'utilise alors que la grille écrite à la main.
    configured: bool
    models: int = 0
    fetched_at: datetime | None = None
    error: str | None = None


class Recommendation(BaseModel):
    query: str
    needs: Needs
    # Le modèle qui a compris la demande, ou « keywords » s'il a fallu s'en passer.
    understood_by: str
    picks: list[ModelPick]
    benchmarks: BenchmarksStatus
    warnings: list[str] = Field(default_factory=list)


# --- Conversations enregistrées ---


class ConversationSummary(BaseModel):
    # from_attributes : ces schémas se construisent directement depuis les objets de l'ORM.
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    project_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class CreateConversationRequest(BaseModel):
    # Le projet auquel rattacher la conversation ; aucun pour une simple discussion.
    project_id: uuid.UUID | None = None


class Source(BaseModel):
    """Un extrait de document retrouvé pour répondre (RAG)."""

    document_id: uuid.UUID
    document_name: str
    page: int | None = None
    content: str
    # Similarité cosinus avec la question : proche de 1 = même sens.
    score: float


class AttachmentInfo(BaseModel):
    """Un fichier joint à une conversation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    name: str
    # Chemin dans le dossier joint (« app/src/main.py ») ; None pour un fichier joint seul.
    path: str | None = None
    # Une image (image/png…) s'affiche, et part telle quelle aux modèles qui savent la lire.
    content_type: str
    size_bytes: int
    # processing : lecture en cours ; ready : utilisable ; error : voir `error`.
    status: Literal["processing", "ready", "error"]
    error: str | None = None
    chunk_count: int
    # Le message qui l'a envoyé ; None tant qu'il attend dans la zone de saisie.
    message_id: uuid.UUID | None = None
    created_at: datetime


class FileDiff(BaseModel):
    """Ce qu'une écriture de l'agent change dans un fichier, présenté comme un `git diff`."""

    path: str
    # Le fichier n'existait pas encore.
    created: bool = False
    added: int
    removed: int
    # Les blocs de changements (« hunks ») : un en-tête « @@ -3,4 +3,6 @@ » (où commence le
    # bloc, et sur combien de lignes, avant et après), puis chaque ligne, préfixée par « + »
    # (ajoutée), « - » (retirée) ou une espace (contexte inchangé, pour se repérer).
    lines: list[str]
    # Trop long pour être montré en entier : seul le début l'est.
    truncated: bool = False


class AgentStep(BaseModel):
    """Un appel d'outil de l'agent, tel qu'on l'affiche et l'enregistre."""

    id: str
    name: str
    # Résumé court affiché dans l'interface : read_file(src/api.ts)
    summary: str
    # done : exécuté ; error : l'outil a échoué ; denied : l'utilisateur a refusé.
    status: Literal["done", "error", "denied"]
    output: str
    # Ce que l'action change, fichier par fichier (ou aurait changé, si elle a été refusée) :
    # un fichier pour write_file et edit_file, tous ceux du commit pour git_commit.
    diffs: list[FileDiff] | None = None
    # L'ancien format, un seul fichier : les réponses enregistrées avant `diffs` le gardent.
    diff: FileDiff | None = None


class ApprovalRequest(BaseModel):
    """La réponse de l'utilisateur à l'agent : une autorisation, ou la réponse à sa question."""

    # Pour une action : once (cette fois), always (pour toute la conversation : l'outil, ou
    # le dossier hors du projet qu'il demandait) ou deny. Pour une question de l'agent
    # (ask_user) : answer, avec le texte choisi.
    decision: Literal["once", "always", "deny", "answer"]
    answer: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def an_answer_needs_text(self) -> Self:
        if self.decision == "answer" and not (self.answer or "").strip():
            raise ValueError("An answer needs some text")
        return self


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
    # Les outils utilisés par l'agent pour produire cette réponse.
    steps: list[AgentStep] | None = None
    # Les fichiers joints à ce message (messages de l'utilisateur).
    attachments: list[AttachmentInfo] = Field(default_factory=list)
    created_at: datetime


class ConversationDetail(ConversationSummary):
    messages: list[StoredMessage]


class SendMessageRequest(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    content: str = Field(min_length=1)
    # Les fichiers joints à ce message : déjà importés dans la conversation, et prêts.
    attachment_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    # Mode agent : le modèle peut lire et modifier les fichiers du projet avec ses outils.
    agent: bool = False


# --- Projets et dossier de travail ---


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    # Le chemin absolu du dossier (l'enregistré tel quel s'il a disparu).
    path: str
    created_at: datetime
    # False si le dossier a disparu depuis (déplacé, renommé, supprimé).
    available: bool
    git_branch: str | None = None
    # Le fichier de consignes transmis au modèle (AGENTS.md ou CLAUDE.md), s'il y en a un.
    instructions_file: str | None = None


class CreateProjectRequest(BaseModel):
    # Relatif au dossier atteignable, comme les chemins du navigateur de dossiers.
    path: str
    # Par défaut : le nom du dossier.
    name: str | None = Field(default=None, max_length=200)


class FolderInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    path: str
    is_git: bool


class DirectoryListing(BaseModel):
    # Le dossier atteignable, tel que le voit le serveur (votre dossier personnel).
    root: str
    # Le dossier listé, relatif au dossier atteignable ("" pour la racine).
    path: str
    # Le dossier parent, ou None à la racine.
    parent: str | None
    directories: list[FolderInfo]


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


class ToolCallEvent(BaseModel):
    """Le modèle demande à utiliser un outil."""

    type: Literal["tool_call"] = "tool_call"
    id: str
    name: str
    # Les arguments tels que le modèle les a écrits : du JSON, parfois mal formé.
    arguments: str


class UsageEvent(BaseModel):
    """Décompte des tokens, envoyé une seule fois à la fin du stream."""

    type: Literal["usage"] = "usage"
    prompt_tokens: int
    completion_tokens: int


StreamEvent = TokenEvent | ReasoningEvent | UsageEvent | ToolCallEvent
