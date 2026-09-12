"""Présenter le projet au modèle : son nom, ce que contient son dossier, ses consignes."""

from pathlib import Path

from netherbrain.agent.prompt import INSTRUCTIONS as AGENT_INSTRUCTIONS
from netherbrain.projects.workspace import instructions_file

# De quoi donner une idée du projet sans noyer le modèle (ni sa fenêtre de contexte).
MAX_ENTRIES = 100
MAX_INSTRUCTIONS_CHARS = 20_000


def list_root(folder: Path) -> str:
    """Le contenu de la racine du projet, un élément par ligne (les dossiers finissent par /)."""
    try:
        children = sorted(folder.iterdir(), key=lambda child: (not child.is_dir(), child.name))
    except OSError:
        return "(the folder cannot be read)"
    names = [
        f"{child.name}/" if child.is_dir() else child.name
        for child in children
        if not child.name.startswith(".")
    ]
    lines = names[:MAX_ENTRIES]
    if len(names) > MAX_ENTRIES:
        lines.append(f"… and {len(names) - MAX_ENTRIES} more")
    return "\n".join(lines) or "(empty folder)"


def read_instructions(folder: Path) -> tuple[str, str] | None:
    """(nom du fichier, contenu) des consignes du projet, tronquées si elles sont trop longues."""
    path = instructions_file(folder)
    if path is None:
        return None
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return None
    if len(text) > MAX_INSTRUCTIONS_CHARS:
        text = text[:MAX_INSTRUCTIONS_CHARS] + "\n[… truncated]"
    return path.name, text


def build_project_context(name: str, folder: Path, agent: bool = False) -> str:
    """Le message système qui situe la conversation dans son projet.

    En anglais, comme les autres consignes : c'est la langue que les modèles suivent le mieux.
    Avec `agent`, le modèle dispose d'outils pour lire et modifier le dossier.
    """
    parts = [
        f'The user is working on the project "{name}". '
        f"Top-level content of its folder:\n{list_root(folder)}"
    ]
    if instructions := read_instructions(folder):
        filename, text = instructions
        parts.append(f"The project's instructions, from {filename}. Follow them:\n\n{text}")
    parts.append(
        AGENT_INSTRUCTIONS
        if agent
        else "You cannot open the project's files yourself: when you need to see some code, "
        "ask the user to paste it."
    )
    parts.append("Always answer in the language of the user's message.")
    return "\n\n".join(parts)
