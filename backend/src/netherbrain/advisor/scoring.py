"""Classer les modèles pour une demande : un score calculé par du code, et expliqué.

Le LLM ne fait que comprendre la demande ; c'est ce module qui décide. Il ne peut donc
recommander que des modèles réels, et chaque note se justifie par des raisons lisibles.
"""

from dataclasses import dataclass, field
from typing import Literal

from netherbrain.advisor.knowledge import SUGGESTIONS, FamilyProfile, installed_key, profile_for
from netherbrain.advisor.matching import BenchmarkIndex, BenchmarkMatch
from netherbrain.advisor.sources import SOURCE_NAME
from netherbrain.schemas import ModelCard, ModelStats, Needs

Role = Literal["best", "fastest", "download", "cloud"]

TASK_LABELS = {
    "code": "Code",
    "reasoning": "Reasoning",
    "writing": "Writing",
    "summary": "Long documents",
    "chat": "Conversation",
    "vision": "Images",
    "agent": "Agents",
    "multilingual": "Languages other than English",
}

# Les tâches que les benchmarks mesurent, et l'indice qui les mesure.
BENCHMARK_METRICS = {
    "code": "coding",
    "reasoning": "math",
    "writing": "intelligence",
    "summary": "intelligence",
    "chat": "intelligence",
}

# Poids de l'adéquation à la tâche et de la vitesse, selon la priorité exprimée.
WEIGHTS = {"quality": (0.75, 0.25), "balanced": (0.6, 0.4), "speed": (0.35, 0.65)}

LONG_CONTEXT = 32_000
# Le contexte (le « KV cache ») occupe aussi de la VRAM, en plus du fichier du modèle.
CONTEXT_OVERHEAD_GB = 1.5
# Ordre de grandeur sur une carte récente : un modèle de 5 Go génère environ 100 tokens/s.
LOCAL_SPEED_FACTOR = 500
# Au-delà, une vitesse est jugée excellente (en local, puis chez un fournisseur cloud).
FAST_LOCAL = 80
FAST_CLOUD = 150
# Une tâche sur laquelle on ne sait rien du modèle : ni bonne ni mauvaise note.
UNKNOWN_SKILL = 0.4


@dataclass
class Candidate:
    model: str
    provider: str | None  # None : pas encore installé
    local: bool
    # Utilisable tout de suite : installé, ou chez un fournisseur distant disponible.
    ready: bool
    capabilities: set[str]
    size_gb: float | None
    context_length: int | None
    free: bool | None
    measured_tps: float | None = None
    profile: FamilyProfile | None = None
    benchmark: BenchmarkMatch | None = None


@dataclass
class Scored:
    candidate: Candidate
    fit: float
    speed: float
    score: float
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def build_candidates(
    cards: list[ModelCard],
    stats: dict[tuple[str, str], ModelStats],
    index: BenchmarkIndex | None,
    *,
    suggest_downloads: bool,
) -> list[Candidate]:
    """Les modèles disponibles, plus ceux qu'on pourrait conseiller de télécharger."""
    candidates = []
    for card in cards:
        if "embedding" in card.capabilities:
            continue  # ils ne savent pas discuter
        measured = stats.get((card.provider, card.id))
        candidates.append(
            Candidate(
                model=card.id,
                provider=card.provider,
                local=card.local,
                ready=True,
                capabilities=set(card.capabilities),
                size_gb=card.size_bytes / 1e9 if card.size_bytes else None,
                context_length=card.context_length,
                free=card.free,
                measured_tps=measured.avg_tokens_per_second if measured else None,
                profile=profile_for(card.id),
                benchmark=index.match(card.id) if index else None,
            )
        )

    # Sans Ollama joignable, on ne sait pas ce qui est installé : on s'abstient de conseiller
    # de télécharger un modèle peut-être déjà là.
    if suggest_downloads:
        installed = {installed_key(c.model) for c in candidates if c.local}
        for suggestion in SUGGESTIONS:
            if installed_key(suggestion.model) in installed:
                continue
            candidates.append(
                Candidate(
                    model=suggestion.model,
                    provider=None,
                    local=True,
                    ready=False,
                    capabilities=set(suggestion.capabilities),
                    size_gb=suggestion.size_gb,
                    context_length=suggestion.context_length,
                    free=True,
                    profile=profile_for(suggestion.model),
                    benchmark=index.match(suggestion.model) if index else None,
                )
            )
    return candidates


def evaluate(candidate: Candidate, needs: Needs, vram_gb: float) -> Scored | None:
    """La note d'un modèle pour ces besoins, ou None s'il ne peut pas convenir du tout."""
    c = candidate
    # Les exigences strictes d'abord : inutile de noter un modèle qui ne peut pas faire.
    if "vision" in needs.requires and "vision" not in c.capabilities:
        return None
    if "tools" in needs.requires and "tools" not in c.capabilities:
        return None
    if needs.local_only and not c.local:
        return None
    too_big = c.local and c.size_gb is not None and c.size_gb + CONTEXT_OVERHEAD_GB > vram_gb
    if too_big and not c.ready:
        return None  # on ne conseille pas de télécharger un modèle qui ne tient pas

    reasons: list[str] = []
    warnings: list[str] = []
    skills = []
    for task in needs.tasks:
        skill, reason = _skill(c, task)
        skills.append(skill)
        if reason:
            reasons.append(reason)
        else:
            warnings.append(f"No data on {TASK_LABELS[task].lower()} for this model")
    fit = sum(skills) / len(skills)

    if "long_context" in needs.requires:
        if c.context_length is None:
            warnings.append("Context length unknown")
        elif c.context_length < LONG_CONTEXT:
            fit *= 0.6
            warnings.append(
                f"Short context ({_thousands(c.context_length)} tokens) for long documents"
            )
        else:
            reasons.append(f"Long context: {_thousands(c.context_length)} tokens")
    if "vision" in needs.requires:
        reasons.append("Reads images")
    if "tools" in needs.requires:
        reasons.append("Can use tools (agent mode)")

    speed, speed_reason = _speed(c, too_big)
    if speed_reason:
        reasons.append(speed_reason)

    if not c.local:
        warnings.append("Runs in the cloud: your requests leave your machine")
        if c.free:
            reasons.append("Free to use")
    elif too_big:
        warnings.append(
            f"{c.size_gb:.1f} GB: more than your {vram_gb:g} GB of VRAM can hold, "
            "expect slow answers"
        )
    elif c.size_gb is not None:
        reasons.append(f"Fits your {vram_gb:g} GB of VRAM ({c.size_gb:.1f} GB)")

    fit_weight, speed_weight = WEIGHTS[needs.priority]
    # Un petit avantage à ce qui est prêt tout de suite, et à ce qui reste sur la machine.
    bonus = (0.05 if c.ready else 0.0) + (0.03 if c.local else 0.0)
    score = fit_weight * fit + speed_weight * speed + bonus
    return Scored(c, fit, speed, score, reasons, warnings)


def recommend_models(
    needs: Needs, candidates: list[Candidate], vram_gb: float
) -> list[tuple[Role, Scored]]:
    """Le podium : le meilleur choix, un compromis plus rapide, et une piste à explorer."""
    scored = sorted(
        (s for c in candidates if (s := evaluate(c, needs, vram_gb)) is not None),
        key=lambda s: s.score,
        reverse=True,
    )
    ready = [s for s in scored if s.candidate.ready]

    picks: list[tuple[Role, Scored]] = []
    if ready:
        best = ready[0]
        picks.append(("best", best))
        # Presque aussi compétent (80 % au moins) mais plus rapide : le bon compromis.
        faster = [s for s in ready[1:] if s.fit >= 0.8 * best.fit and s.speed > best.speed]
        if faster:
            picks.append(("fastest", max(faster, key=lambda s: s.speed)))

    taken = {id(s) for _, s in picks}
    best_fit = picks[0][1].fit if picks else 0.0
    downloads = [s for s in scored if not s.candidate.ready]
    cloud = [s for s in ready if not s.candidate.local and id(s) not in taken]
    # À télécharger seulement s'il fait mieux que ce qu'on a déjà.
    better = next((s for s in downloads if s.fit > best_fit), None)
    if better:
        picks.append(("download", better))
    elif cloud:
        picks.append(("cloud", cloud[0]))
    elif downloads and not picks:
        picks.append(("download", downloads[0]))
    return picks


def _skill(c: Candidate, task: str) -> tuple[float, str | None]:
    """L'aptitude à une tâche (de 0 à 1), et ce qui la justifie."""
    label = TASK_LABELS[task]
    grid = c.profile.strengths.get(task) if c.profile else None
    metric = BENCHMARK_METRICS.get(task)
    measured = c.benchmark.percentiles.get(metric) if c.benchmark and metric else None

    if measured is not None:
        # Le benchmark mesure le modèle réel ; la grille corrige ce qu'il ne voit pas.
        skill = measured if grid is None else (measured + grid / 5) / 2
        percent = round(measured * 100)
        return skill, f"{label}: better than {percent}% of the models benchmarked by {SOURCE_NAME}"
    if grid is not None:
        return grid / 5, f"{label}: {grid}/5 in Netherbrain's model grid"
    return UNKNOWN_SKILL, None


def _speed(c: Candidate, too_big: bool) -> tuple[float, str | None]:
    """La vitesse (de 0 à 1) : mesurée ici si possible, sinon estimée."""
    if c.measured_tps:
        return min(c.measured_tps / FAST_LOCAL, 1.0), f"Measured here: {c.measured_tps:g} tok/s"
    if c.local and c.size_gb:
        # Un modèle qui déborde de la VRAM passe en partie sur le processeur : bien plus lent.
        estimate = LOCAL_SPEED_FACTOR / c.size_gb / (5 if too_big else 1)
        return min(
            estimate / FAST_LOCAL, 1.0
        ), f"About {round(estimate)} tok/s expected on your GPU"
    if c.benchmark and c.benchmark.output_speed:
        speed = c.benchmark.output_speed
        return min(speed / FAST_CLOUD, 1.0), f"About {round(speed)} tok/s at cloud providers"
    return 0.5, None


def _thousands(tokens: int) -> str:
    return f"{round(tokens / 1000)}K"
