"""Git pour l'agent : l'état du dépôt, ses différences, et des commits sur autorisation.

Git est lancé sans shell (une liste d'arguments), dans le dossier du projet, avec une
configuration neutre : ni celle de l'utilisateur (alias, pager, diff externe), ni les hooks
du dépôt. Un dépôt piégé ne doit pas pouvoir exécuter du code au moment d'un commit que
l'utilisateur croit anodin.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

from netherbrain.agent.diff import diff_from_lines
from netherbrain.agent.environment import command_environment
from netherbrain.schemas import FileDiff

# Les commits de l'agent sont signés à son nom : l'historique dit qui a fait quoi.
AGENT_NAME = "Netherbrain agent"
AGENT_EMAIL = "agent@netherbrain.invalid"

GIT_OPTIONS = (
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "commit.gpgsign=false",
    # Les chemins accentués ou avec des espaces restent lisibles, au lieu de « \303\251 ».
    "-c",
    "core.quotePath=false",
)


class GitError(Exception):
    """Git a refusé ou échoué ; le message part au modèle."""


def is_git_repository(folder: Path) -> bool:
    return shutil.which("git") is not None and (folder / ".git").exists()


def run_git(folder: Path, *arguments: str, timeout: float) -> str:
    environment = command_environment(os.environ) | {
        # Jamais de question interactive (identifiants…) : elle bloquerait la réponse.
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": AGENT_NAME,
        "GIT_AUTHOR_EMAIL": AGENT_EMAIL,
        "GIT_COMMITTER_NAME": AGENT_NAME,
        "GIT_COMMITTER_EMAIL": AGENT_EMAIL,
    }
    try:
        done = subprocess.run(
            ["git", *GIT_OPTIONS, *arguments],
            cwd=folder,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=environment,
        )
    except subprocess.TimeoutExpired:
        raise GitError(f"git {arguments[0]} stopped after {timeout:g}s") from None
    except OSError as exc:
        raise GitError(f"git cannot run: {exc.strerror or exc}") from exc
    if done.returncode != 0:
        raise GitError((done.stderr or done.stdout).strip() or f"git {arguments[0]} failed")
    return done.stdout


def parse_diff(output: str) -> list[FileDiff]:
    """La sortie de `git diff` pour plusieurs fichiers, découpée en un diff par fichier."""
    diffs = []
    for block in re.split(r"^diff --git ", output, flags=re.MULTILINE)[1:]:
        lines = block.splitlines()
        header = lines[: next((i for i, line in enumerate(lines) if line.startswith("@@")), None)]
        diffs.append(
            diff_from_lines(
                _path(lines[0], header),
                lines[len(header) :],
                created=any(line.startswith("new file mode") for line in header),
            )
        )
    return diffs


def _path(first_line: str, header: list[str]) -> str:
    # « +++ b/chemin » (ou « --- a/chemin » pour un fichier supprimé). Git ajoute une tabulation
    # après un nom qui contient des espaces.
    for prefix in ("+++ b/", "--- a/"):
        line = next((line for line in header if line.startswith(prefix)), None)
        if line is not None:
            return line.removeprefix(prefix).rstrip("\t")
    # Fichier binaire : pas de lignes ---/+++, seulement « a/chemin b/chemin ».
    return first_line.split(" b/", 1)[-1]
