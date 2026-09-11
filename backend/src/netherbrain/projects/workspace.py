"""Le dossier de travail : là où vivent les projets, et d'où l'on ne sort jamais.

Tous les chemins venus de l'extérieur (le navigateur, et bientôt le modèle) sont relatifs à
ce dossier. `Workspace.resolve` garantit qu'aucun ne permet d'en sortir : ni avec « .. », ni
avec un chemin absolu, ni en passant par un lien symbolique.
"""

from dataclasses import dataclass
from pathlib import Path

# Fichiers de consignes lus à la racine d'un projet, dans cet ordre. AGENTS.md est le format
# ouvert partagé par plusieurs outils de code ; CLAUDE.md, celui de Claude Code.
INSTRUCTION_FILES = ("AGENTS.md", "CLAUDE.md")


class WorkspaceError(Exception):
    """Chemin refusé : hors du dossier de travail, ou illisible."""


class FolderNotFoundError(WorkspaceError):
    """Le dossier demandé n'existe pas (ou ce n'est pas un dossier)."""


@dataclass(frozen=True)
class DirectoryEntry:
    name: str
    # Relatif au dossier de travail, avec des « / » : c'est ce qu'on stocke et ce qu'on affiche.
    path: str
    is_git: bool


class Workspace:
    def __init__(self, root: Path) -> None:
        # resolve() : chemin absolu, sans « .. » ni lien symbolique. Toutes les vérifications
        # comparent des chemins résolus.
        self.root = root.expanduser().resolve()

    def resolve(self, relative: str) -> Path:
        """Le chemin absolu de `relative`, garanti à l'intérieur du dossier de travail."""
        if Path(relative).is_absolute():
            raise WorkspaceError("Paths must be relative to the workspace")
        # resolve() suit aussi les liens symboliques : un lien qui pointe vers l'extérieur
        # est donc démasqué ici, pas seulement les « .. ».
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise WorkspaceError("This path is outside the workspace")
        return path

    def relative(self, path: Path) -> str:
        """Le chemin tel qu'on le stocke : relatif au dossier de travail ("" pour la racine)."""
        return "" if path == self.root else path.relative_to(self.root).as_posix()

    def directory(self, relative: str) -> Path:
        path = self.resolve(relative)
        if path == self.root and not path.is_dir():
            raise FolderNotFoundError(
                f"The workspace folder {self.root} does not exist: "
                "create it, or set NETHERBRAIN_WORKSPACE_ROOT"
            )
        if not path.is_dir():
            raise FolderNotFoundError(f"Folder not found in the workspace: {relative}")
        return path

    def find(self, relative: str) -> Path | None:
        """Le dossier, ou None s'il a disparu (déplacé, supprimé) ou s'il est devenu interdit."""
        try:
            return self.directory(relative)
        except WorkspaceError:
            return None

    def list_directories(self, relative: str = "") -> list[DirectoryEntry]:
        """Les sous-dossiers visibles (pas ceux qui commencent par un point), triés par nom."""
        folder = self.directory(relative)
        try:
            children = sorted(folder.iterdir(), key=lambda child: child.name.lower())
        except OSError as exc:
            raise WorkspaceError(f"Cannot read this folder: {exc.strerror}") from exc

        entries = []
        for child in children:
            if child.name.startswith(".") or not child.is_dir():
                continue
            path = child.resolve()
            if not path.is_relative_to(self.root):
                continue  # lien symbolique vers l'extérieur : on ne le propose même pas
            entries.append(
                DirectoryEntry(child.name, self.relative(path), (path / ".git").exists())
            )
        return entries


def git_branch(folder: Path) -> str | None:
    """La branche Git en cours, lue directement dans .git/HEAD (sans lancer git)."""
    try:
        head = (folder / ".git" / "HEAD").read_text().strip()
    except OSError:
        return None  # pas un dépôt Git (ou un « worktree », dont .git est un fichier)
    if head.startswith("ref: refs/heads/"):
        return head.removeprefix("ref: refs/heads/")
    # « HEAD détachée » : HEAD contient directement un identifiant de commit.
    return head[:7] or None


def instructions_file(folder: Path) -> Path | None:
    """Le fichier de consignes du projet (AGENTS.md ou CLAUDE.md), s'il y en a un."""
    return next(
        (folder / name for name in INSTRUCTION_FILES if (folder / name).is_file()),
        None,
    )
