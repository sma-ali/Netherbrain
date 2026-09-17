"""Comprendre la demande avec un LLM : une phrase libre devient des besoins précis."""

from dataclasses import dataclass

from netherbrain.advisor.knowledge import compact
from netherbrain.providers import LLMProvider, ProviderResult
from netherbrain.schemas import ChatMessage, ModelCard, Needs

# En anglais, comme les autres consignes : c'est la langue que les modèles suivent le mieux.
INSTRUCTIONS = """You help someone choose a language model. Read their request and describe what \
the model needs to be good at.
- tasks: 1 to 3, the most important first, among: code (programming), reasoning (maths, logic, \
planning), writing (articles, emails, stories), summary (long documents, PDFs, reports), \
chat (general assistant), vision (images, screenshots, scans), agent (acts with tools: files, \
commands, automation), multilingual (the answers must be in a language other than English).
- requires: only what is strictly necessary among vision (reads images), tools (calls \
functions), long_context (very long documents). PDFs and other documents are read as text: \
they need long_context, never vision. vision is only for images, photos, screenshots or scans.
- priority: speed if they want fast answers, quality if they insist on the best results, \
balanced otherwise.
- local_only: true only if they mention privacy, confidential data or offline use."""

# Les familles qui suivent bien un format imposé, de la plus fiable à la moins fiable.
PREFERRED_FAMILIES = (
    "qwen3.5",
    "qwen3",
    "gemma4",
    "gpt-oss",
    "mistral",
    "llama",
    "gemma",
    "ornith",
)


@dataclass(frozen=True)
class AdvisorModel:
    provider: str
    model: str
    # Un modèle qui réfléchit avant de répondre : on coupe la réflexion, inutile ici et lente.
    reasoning: bool


def pick_advisor_model(
    results: list[ProviderResult[ModelCard]],
    configured: str | None,
    loaded: frozenset[str] = frozenset(),
) -> AdvisorModel | None:
    """Le modèle qui lira la demande : celui de la configuration, sinon un modèle local.

    De préférence un modèle déjà chargé en VRAM (`loaded`) : en charger un second prendrait
    plusieurs secondes, et pourrait chasser de la mémoire celui avec lequel on discute.
    """
    cards = [
        card
        for result in results
        if result.error is None
        for card in result.items
        if "embedding" not in card.capabilities
    ]
    if configured:
        provider, _, model = configured.partition("/")
        card = next((c for c in cards if c.provider == provider and c.id == model), None)
        return AdvisorModel(provider, model, bool(card and "reasoning" in card.capabilities))

    local = [card for card in cards if card.local]
    if local:

        def preference(card: ModelCard) -> tuple[int, int, int]:
            key = compact(card.id)
            rank = next(
                (
                    i
                    for i, family in enumerate(PREFERRED_FAMILIES)
                    if key.startswith(compact(family))
                ),
                len(PREFERRED_FAMILIES),
            )
            # Déjà chargé d'abord ; puis la famille la plus fiable ; puis le plus petit.
            return (0 if card.id in loaded else 1), rank, card.size_bytes or 0

        chosen = min(local, key=preference)
    elif cards:
        chosen = cards[0]
    else:
        return None
    return AdvisorModel(chosen.provider, chosen.id, "reasoning" in chosen.capabilities)


async def understand(query: str, provider: LLMProvider, advisor: AdvisorModel) -> Needs:
    """Les besoins, au format imposé par le schéma JSON de `Needs` (sortie structurée).

    Lève ProviderError ou une erreur de validation : l'appelant se rabat alors sur les
    mots-clés. C'est aussi à lui de borner le temps d'attente.
    """
    messages = [
        ChatMessage(role="system", content=INSTRUCTIONS),
        ChatMessage(role="user", content=query),
    ]
    raw = await provider.complete_json(
        advisor.model,
        messages,
        Needs.model_json_schema(),
        think=False if advisor.reasoning else None,
    )
    return Needs.model_validate(raw)
