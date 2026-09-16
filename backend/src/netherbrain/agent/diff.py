"""Ce qu'une écriture de l'agent changerait : un diff unifié, le format de `git diff`."""

import difflib

from netherbrain.schemas import FileDiff

# Au-delà, le diff est coupé : il sert à relire, pas à tout afficher d'un fichier généré.
MAX_DIFF_LINES = 400
MAX_LINE_CHARS = 500
# Lignes de contexte autour de chaque changement, comme git.
CONTEXT_LINES = 3


def make_diff(path: str, old: str, new: str, *, created: bool = False) -> FileDiff:
    """Le diff entre deux versions d'un fichier (vide si elles sont identiques)."""
    # difflib compare des listes de lignes : il trouve la plus longue suite commune, et en
    # déduit le minimum de lignes à retirer et à ajouter.
    changes = difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=CONTEXT_LINES)
    # Les deux premières lignes (« --- » et « +++ ») répètent le nom du fichier : inutiles ici.
    lines = [line for index, line in enumerate(changes) if index >= 2]
    return FileDiff(
        path=path,
        created=created,
        added=sum(1 for line in lines if line.startswith("+")),
        removed=sum(1 for line in lines if line.startswith("-")),
        lines=[_shorten(line) for line in lines[:MAX_DIFF_LINES]],
        truncated=len(lines) > MAX_DIFF_LINES,
    )


def _shorten(line: str) -> str:
    return line if len(line) <= MAX_LINE_CHARS else line[:MAX_LINE_CHARS] + "…"
