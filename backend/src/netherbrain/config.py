from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration de l'application, lue depuis les variables d'environnement (ou un .env)."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="NETHERBRAIN_", extra="ignore")

    # Base PostgreSQL. Par défaut, celle du service « db » de Compose, publiée sur localhost.
    database_url: str = "postgresql+asyncpg://netherbrain:netherbrain@localhost:5432/netherbrain"

    # Fournisseur local : toujours activé.
    ollama_base_url: str = "http://localhost:11434/v1"
    # Fenêtre de contexte demandée à Ollama (0 : sa valeur par défaut, 4096 tokens, trop
    # courte pour l'agent). Plus elle est grande, plus le modèle occupe de VRAM.
    ollama_context_length: int = 16384

    # Fournisseurs distants : activés seulement si leur clé d'API est renseignée.
    # SecretStr garde les clés hors des logs, des tracebacks et de repr().
    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_free_only: bool = True
    # Serveur llama.cpp lancé à la main (llama-server), pour les modèles qu'Ollama ne sait pas
    # lire, comme les GGUF ternaires. Vide : le fournisseur est désactivé.
    llamacpp_base_url: str | None = None
    groq_api_key: SecretStr | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # Délai max accordé à chaque fournisseur par /api/models avant de le déclarer indisponible.
    provider_list_timeout: float = 5.0

    # --- RAG : discuter avec ses documents ---
    # Modèle d'embeddings servi par Ollama. Il doit produire des vecteurs de 768 dimensions,
    # la taille de la colonne en base.
    embedding_model: str = "nomic-embed-text"
    # nomic-embed-text attend un préfixe qui indique le rôle du texte : document ou question.
    embedding_document_prefix: str = "search_document: "
    embedding_query_prefix: str = "search_query: "
    # Nombre d'extraits ajoutés au prompt, et découpage des documents (en caractères).
    rag_top_k: int = 5
    chunk_size: int = 1200
    chunk_overlap: int = 200
    max_upload_mb: int = 20
    # Fichiers joints au chat : tant que leur texte tient dans ce nombre de caractères (au
    # total), le modèle les reçoit en entier ; au-delà, seulement les passages utiles.
    attachment_inline_chars: int = 32_000
    # Images jointes : seules les plus récentes partent au modèle à chaque message, car
    # chacune coûte des centaines de tokens (et le modèle relit tout l'historique).
    max_images_sent: int = 8

    # --- Conseiller de modèles ---
    # Clé de l'API gratuite d'Artificial Analysis (https://artificialanalysis.ai/) : des
    # benchmarks publics mis à jour en continu. Sans elle, seule la grille écrite à la main sert.
    artificial_analysis_api_key: SecretStr | None = None
    artificial_analysis_base_url: str = "https://artificialanalysis.ai/api/v2"
    # Âge au-delà duquel on redemande les benchmarks (l'API limite à 1 000 requêtes par jour).
    benchmarks_max_age_hours: float = 24
    # Le modèle qui lit la demande, « fournisseur/modèle » ; vide : un modèle local choisi seul.
    advisor_model: str | None = None
    advisor_timeout: float = 60
    # La VRAM de la carte graphique, pour savoir quels modèles locaux y tiennent.
    gpu_vram_gb: float = 16

    # --- Projets ---
    # Le dossier de travail : chaque projet est l'un de ses sous-dossiers, et l'application
    # n'accède jamais à rien en dehors. Un dossier dédié plutôt que tous vos projets : l'agent
    # n'a accès qu'à ce que vous y mettez. Dans Docker, c'est le dossier monté sur /workspace.
    workspace_root: Path = Path.home() / "netherbrain-workspace"

    # --- Agent de code ---
    # Nombre maximum d'allers-retours modèle → outils pour une seule question.
    agent_max_steps: int = 12
    # Taille maximale du résultat d'un outil renvoyé au modèle (en caractères).
    agent_max_output_chars: int = 8000
    # Secondes accordées à une commande lancée par l'agent, puis à l'utilisateur pour
    # accepter ou refuser une action.
    agent_command_timeout: int = 120
    agent_approval_timeout: float = 300.0
    # False : l'agent ne peut que lire et modifier des fichiers, sans lancer de commande.
    agent_allow_commands: bool = True

    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
