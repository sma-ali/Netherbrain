"""Ce qu'on sait des familles de modèles : la « grille de forces », écrite à la main.

Elle sert quand aucun benchmark en ligne ne couvre un modèle (les petites versions
quantifiées, souvent), et pour ce que les benchmarks ne mesurent pas : l'aisance hors de
l'anglais, ou comme agent. Notes indicatives de 1 à 5, relatives à la taille du modèle.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FamilyProfile:
    prefix: str
    strengths: dict[str, int]


def compact(name: str) -> str:
    """Un nom sans éditeur ni ponctuation : « google/gemma-4-12b » → « gemma412b »."""
    return re.sub(r"[^a-z0-9]", "", name.lower().rsplit("/", 1)[-1])


# La première correspondance l'emporte : les préfixes les plus précis en tête.
FAMILIES: list[FamilyProfile] = [
    FamilyProfile(
        "deepseek-r1",
        {
            "reasoning": 5,
            "code": 3,
            "summary": 3,
            "writing": 2,
            "chat": 2,
            "multilingual": 3,
            "agent": 2,
        },
    ),
    FamilyProfile(
        "qwen3-coder",
        {
            "code": 5,
            "agent": 4,
            "reasoning": 3,
            "summary": 3,
            "writing": 2,
            "chat": 2,
            "multilingual": 3,
        },
    ),
    FamilyProfile(
        "qwen3.5",
        {
            "code": 4,
            "reasoning": 4,
            "writing": 4,
            "summary": 4,
            "chat": 4,
            "multilingual": 4,
            "agent": 4,
            "vision": 4,
        },
    ),
    FamilyProfile(
        "qwen3",
        {
            "code": 4,
            "reasoning": 4,
            "writing": 3,
            "summary": 3,
            "chat": 4,
            "multilingual": 4,
            "agent": 4,
        },
    ),
    FamilyProfile(
        "qwen",
        {
            "code": 4,
            "reasoning": 3,
            "writing": 3,
            "summary": 3,
            "chat": 3,
            "multilingual": 4,
            "agent": 3,
        },
    ),
    FamilyProfile(
        "ornith",
        {
            "code": 5,
            "agent": 5,
            "reasoning": 3,
            "summary": 3,
            "chat": 3,
            "writing": 2,
            "multilingual": 2,
        },
    ),
    FamilyProfile(
        "gemma4",
        {
            "writing": 4,
            "multilingual": 5,
            "summary": 4,
            "chat": 4,
            "vision": 4,
            "code": 3,
            "reasoning": 3,
            "agent": 3,
        },
    ),
    FamilyProfile(
        "gemma",
        {
            "writing": 4,
            "multilingual": 4,
            "summary": 3,
            "chat": 4,
            "vision": 3,
            "code": 2,
            "reasoning": 2,
            "agent": 2,
        },
    ),
    FamilyProfile(
        "gpt-oss",
        {
            "reasoning": 5,
            "code": 4,
            "agent": 4,
            "writing": 3,
            "summary": 3,
            "chat": 3,
            "multilingual": 3,
        },
    ),
    FamilyProfile(
        "devstral",
        {
            "code": 5,
            "agent": 5,
            "reasoning": 3,
            "summary": 2,
            "writing": 2,
            "chat": 2,
            "multilingual": 2,
        },
    ),
    FamilyProfile(
        "magistral",
        {
            "reasoning": 4,
            "multilingual": 5,
            "writing": 4,
            "code": 3,
            "summary": 3,
            "chat": 3,
            "agent": 3,
        },
    ),
    FamilyProfile(
        "mistral",
        {
            "multilingual": 5,
            "writing": 4,
            "chat": 4,
            "summary": 4,
            "code": 3,
            "reasoning": 3,
            "agent": 3,
            "vision": 3,
        },
    ),
    FamilyProfile(
        "llama",
        {
            "chat": 4,
            "writing": 3,
            "summary": 3,
            "code": 3,
            "reasoning": 2,
            "multilingual": 3,
            "agent": 3,
        },
    ),
    FamilyProfile(
        "phi",
        {
            "reasoning": 4,
            "code": 3,
            "summary": 3,
            "chat": 3,
            "writing": 2,
            "multilingual": 2,
            "agent": 2,
        },
    ),
    FamilyProfile(
        "granite",
        {
            "agent": 4,
            "summary": 3,
            "code": 3,
            "chat": 3,
            "writing": 3,
            "reasoning": 2,
            "multilingual": 3,
        },
    ),
    FamilyProfile(
        "nemotron",
        {
            "reasoning": 4,
            "agent": 4,
            "code": 4,
            "chat": 3,
            "writing": 3,
            "summary": 3,
            "multilingual": 2,
        },
    ),
    FamilyProfile(
        "glm",
        {
            "code": 5,
            "agent": 5,
            "reasoning": 4,
            "writing": 3,
            "summary": 3,
            "chat": 3,
            "multilingual": 3,
        },
    ),
    FamilyProfile(
        "deepseek",
        {
            "code": 4,
            "reasoning": 4,
            "agent": 4,
            "writing": 3,
            "summary": 3,
            "chat": 3,
            "multilingual": 3,
        },
    ),
]


def profile_for(model_id: str) -> FamilyProfile | None:
    key = compact(model_id)
    return next((family for family in FAMILIES if key.startswith(compact(family.prefix))), None)


@dataclass(frozen=True)
class Suggestion:
    """Un modèle local qu'on peut conseiller de télécharger, s'il n'est pas déjà installé."""

    model: str  # le nom à donner à `ollama pull`
    size_gb: float
    capabilities: tuple[str, ...]
    context_length: int


# Tailles relevées sur ollama.com (version quantifiée par défaut de chaque modèle).
SUGGESTIONS: list[Suggestion] = [
    Suggestion("qwen3.5:9b", 6.6, ("reasoning", "tools", "vision"), 262_144),
    Suggestion("gemma4:12b", 7.6, ("reasoning", "tools", "vision"), 262_144),
    Suggestion("ornith:9b", 5.6, ("tools",), 262_144),
    Suggestion("qwen3:8b", 5.2, ("reasoning", "tools"), 40_960),
    Suggestion("deepseek-r1:14b", 9.0, ("reasoning", "tools"), 131_072),
    Suggestion("phi4:14b", 9.1, (), 16_384),
    Suggestion("llama3.1:8b", 4.9, ("tools",), 131_072),
    Suggestion("gpt-oss:20b", 14.0, ("reasoning", "tools"), 131_072),
    Suggestion("devstral:24b", 14.0, ("tools",), 131_072),
    Suggestion("mistral-small:24b", 14.0, ("tools",), 32_768),
]


def installed_key(model: str) -> str:
    """« qwen3 » et « qwen3:latest » désignent le même modèle Ollama."""
    name = model.lower()
    return name if ":" in name else f"{name}:latest"
