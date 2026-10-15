"""Les dossiers que l'application peut atteindre, et d'où l'on ne sort jamais.

`Workspace` confine des chemins relatifs à une racine : ni « .. », ni chemin absolu, ni lien
symbolique n'en sort. Deux racines s'en servent : le dossier atteignable (votre dossier
personnel, NETHERBRAIN_ACCESS_ROOT), où l'on choisit un projet et où l'agent peut demander
l'accès à un dossier ; et l'ancien dossier de travail, base des chemins relatifs des projets
créés avant que les projets puissent être n'importe où.
"""

from dataclasses import dataclass
from pathlib import Path

# Fichiers de consignes lus à la racine d'un projet, dans cet ordre. AGENTS.md est le format
# ouvert partagé par plusieurs outils de code ; CLAUDE.md, celui de Claude Code.
INSTRUCTION_FILES = ("AGENTS.md", "CLAUDE.md")

# Les dossiers de secrets, relatifs au dossier atteignable : l'agent doit demander à chaque
# fois, même dans un dossier autorisé pour toute la conversation.
SECRET_FOLDERS = (
    ".ssh",
    ".gnupg",
    ".aws",
    ".azure",
    ".kube",
    ".docker",
    ".claude",
    ".password-store",
    ".config/cles",
    ".config/usine",
    ".config/gh",
    ".config/gcloud",
)
# Comparés en minuscules. Les fichiers de démarrage du shell en font partie : y écrire, c'est
# faire exécuter une commande à la prochaine ouverture d'un terminal.
SECRET_FILES = frozenset(
    {
        ".env",
        ".netrc",
        ".git-credentials",
        ".pgpass",
        ".npmrc",
        ".pypirc",
        ".bash_history",
        ".zsh_history",
        ".python_history",
        ".bashrc",
        ".zshrc",
        ".profile",
        ".bash_profile",
        ".zprofile",
        ".zshenv",
    }
)
# Les clés privées, où qu'elles soient : id_rsa, id_ed25519… et leurs extensions habituelles.
SECRET_PREFIXES = ("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519")
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".keystore", ".jks")
# Dans un dépôt, un hook ou la config de Git font exécuter des commandes au prochain appel.
GIT_RUNS_CODE = ("hooks", "config")
# Les modèles de .env ne contiennent pas de vraies clés : .env.example reste un fichier ordinaire.
TEMPLATE_SUFFIXES = (".example", ".sample", ".template", ".dist")


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


def is_sensitive(path: Path, home: Path) -> bool:
    """Un fichier ou dossier de secrets : un .env, une clé privée, ce qui vit dans ~/.ssh ou
    ~/.config/cles, ou un fichier qui ferait exécuter du code (~/.bashrc, .git/hooks).

    `path` et `home` sont résolus : un lien symbolique vers ~/.config/cles est démasqué.
    """
    name = path.name.lower()
    if name in SECRET_FILES or name.endswith(SECRET_SUFFIXES):
        return True
    if name.startswith(SECRET_PREFIXES) and not name.endswith(".pub"):
        return True
    if name.startswith(".env.") and not name.endswith(TEMPLATE_SUFFIXES):
        return True
    parts = path.parts
    if any(a == ".git" and b in GIT_RUNS_CODE for a, b in zip(parts, parts[1:], strict=False)):
        return True
    return any(path.is_relative_to(home / folder) for folder in SECRET_FOLDERS)


def locate_project(stored: str, reach: Workspace, legacy: Workspace) -> Path | None:
    """Le dossier d'un projet, ou None s'il a disparu ou n'est plus atteignable.

    Un projet récent est enregistré par son chemin absolu ; un ancien, par son chemin relatif
    à l'ancien dossier de travail.
    """
    path = Path(stored)
    if not path.is_absolute():
        return legacy.find(stored)
    folder = path.resolve()
    return folder if folder.is_relative_to(reach.root) and folder.is_dir() else None
