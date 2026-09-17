"""Comprendre une demande sans LLM, par mots-clés : la solution de secours du conseiller."""

import re

from netherbrain.schemas import Needs, Task

# Les tâches les plus distinctives d'abord : on n'en garde que trois.
KEYWORDS: dict[Task, tuple[str, ...]] = {
    "vision": (
        "image",
        "photo",
        "capture",
        "screenshot",
        "schéma",
        "diagram",
        "vision",
        "ocr",
        "maquette",
        "scan",
    ),
    "code": (
        "code",
        "coder",
        "programm",
        "développ",
        "develop",
        "bug",
        "debug",
        "refactor",
        "python",
        "javascript",
        "typescript",
        "react",
        "api",
        "script",
        "site web",
        "website",
        "backend",
        "frontend",
    ),
    "agent": ("agent", "outil", "tool", "automatis", "automat", "workflow", "commande"),
    "reasoning": (
        "math",
        "logique",
        "logic",
        "raisonn",
        "reason",
        "calcul",
        "énigme",
        "puzzle",
        "démonstr",
        "proof",
        "planif",
        "plan",
    ),
    "summary": (
        "résum",
        "summar",
        "synthès",
        "pdf",
        "document",
        "rapport",
        "report",
        "livre",
        "book",
    ),
    "writing": (
        "écri",
        "rédig",
        "write",
        "article",
        "blog",
        "mail",
        "histoire",
        "story",
        "roman",
        "texte",
        "traduction",
        "translat",
        "poème",
        "poem",
    ),
    "multilingual": (
        "français",
        "french",
        "anglais",
        "espagnol",
        "spanish",
        "allemand",
        "german",
        "multiling",
        "langue",
    ),
    "chat": ("discut", "chat", "conversation", "assistant", "bot", "question"),
}
SPEED = ("rapide", "vite", "fast", "quick", "temps réel", "real-time", "réactif", "léger", "light")
QUALITY = (
    "meilleur",
    "best",
    "qualité",
    "quality",
    "précis",
    "accurate",
    "complexe",
    "complex",
    "pro",
)
LOCAL = (
    "local",
    "hors ligne",
    "offline",
    "confidenti",
    "privé",
    "private",
    "sans internet",
    "rgpd",
    "gdpr",
)


def _found(text: str, keywords: tuple[str, ...]) -> bool:
    # \b : le mot-clé doit commencer un mot. Sans ça, « rapide » contiendrait « api ».
    return any(re.search(rf"\b{re.escape(keyword)}", text) for keyword in keywords)


def needs_from_keywords(query: str) -> Needs:
    text = query.lower()
    tasks: list[Task] = [task for task, words in KEYWORDS.items() if _found(text, words)]
    tasks = tasks[:3] or ["chat"]

    requires = []
    if "vision" in tasks:
        requires.append("vision")
    if "agent" in tasks:
        requires.append("tools")
    if "summary" in tasks:
        requires.append("long_context")

    priority = (
        "speed" if _found(text, SPEED) else "quality" if _found(text, QUALITY) else "balanced"
    )
    return Needs(tasks=tasks, requires=requires, priority=priority, local_only=_found(text, LOCAL))
