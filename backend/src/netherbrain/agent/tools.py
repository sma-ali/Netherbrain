"""Les outils que le modèle peut demander : lister, lire, chercher, écrire, exécuter.

Le projet est le seul dossier ouvert d'office. Un chemin absolu (ou commençant par « ~ »)
peut viser un autre dossier du dossier atteignable, mais seulement avec l'accord de
l'utilisateur : `Toolbox.access` dit quel accord il faut, et `Toolbox.run` refuse tout chemin
hors des dossiers autorisés pour cet appel. Ni « .. », ni lien symbolique ne contourne cette
garde : les chemins sont résolus avant d'être comparés.
"""

import os
import re
import subprocess
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import anyio

from netherbrain.agent.diff import make_diff
from netherbrain.agent.environment import command_environment
from netherbrain.agent.git import GitError, is_git_repository, parse_diff, run_git
from netherbrain.projects.workspace import Workspace, WorkspaceError, is_sensitive
from netherbrain.schemas import FileDiff

T = TypeVar("T")

# Dossiers sans intérêt pour l'agent, qui feraient surtout exploser les listings.
IGNORED = frozenset(
    {
        "node_modules",
        "__pycache__",
        "venv",
        "dist",
        "build",
        "target",
        "coverage",
    }
)


# Les outils qui visent un chemin, et peuvent donc sortir du projet avec l'accord de l'utilisateur.
PATH_TOOLS = frozenset({"list_files", "read_file", "search_files", "write_file", "edit_file"})


class ToolError(Exception):
    """Un outil n'a pas pu faire ce qu'on lui demandait ; le message part au modèle."""


@dataclass
class ToolResult:
    output: str
    error: bool = False


@dataclass(frozen=True)
class Access:
    """L'accord qu'un appel demande, en plus de celui de l'outil lui-même."""

    # Le dossier à ouvrir, hors du projet : celui que « toute la conversation » autoriserait.
    # None quand le chemin est déjà dans le projet ou dans un dossier autorisé.
    folder: Path | None
    # Un fichier de secrets : l'accord ne vaut que pour cet appel, jamais pour la suite.
    sensitive: bool


def _schema(name: str, description: str, properties: dict, required: list[str]) -> dict:
    """Une fonction décrite au format d'OpenAI, celui que comprennent aussi Ollama et Groq."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


STRING = {"type": "string"}
INTEGER = {"type": "integer"}
OUTSIDE = " Outside the project: an absolute path or ~/..., which asks the user for access."

# Proposés seulement dans un dépôt Git, quand git est installé.
GIT_TOOLS = frozenset({"git_status", "git_diff", "git_log", "git_commit"})
# Au-delà, un commit n'est pas prévisualisé en entier (il enregistre quand même tout).
MAX_PREVIEW_FILES = 20
MAX_PREVIEW_BYTES = 200_000

# Un outil à part : il n'agit pas sur les fichiers, il pose une question à l'utilisateur,
# qui répond en cliquant sur l'une des propositions (ou en écrivant sa propre réponse).
ASK_USER = "ask_user"

SCHEMAS = [
    _schema(
        "list_files",
        "List the files and folders of the project, recursively.",
        {
            "path": {
                **STRING,
                "description": "Folder, relative to the project root. Default: '.'." + OUTSIDE,
            }
        },
        [],
    ),
    _schema(
        "read_file",
        "Read a text file of the project. The answer is numbered, like `cat -n`.",
        {
            "path": {**STRING, "description": "File, relative to the project root." + OUTSIDE},
            "offset": {**INTEGER, "description": "First line to read (1 by default)."},
            "limit": {**INTEGER, "description": "How many lines to read (400 by default)."},
        },
        ["path"],
    ),
    _schema(
        "search_files",
        "Search a regular expression in the project's text files, like grep.",
        {
            "pattern": {**STRING, "description": "Python regular expression."},
            "path": {**STRING, "description": "Folder to search in. Default: '.'." + OUTSIDE},
        },
        ["pattern"],
    ),
    _schema(
        "write_file",
        "Create a file or replace its whole content. Asks the user for permission.",
        {
            "path": {**STRING, "description": "Relative to the project root." + OUTSIDE},
            "content": STRING,
        },
        ["path", "content"],
    ),
    _schema(
        "edit_file",
        "Replace one exact excerpt of a file, which must appear exactly once. "
        "Asks the user for permission.",
        {
            "path": {**STRING, "description": "Relative to the project root." + OUTSIDE},
            "old_string": STRING,
            "new_string": STRING,
        },
        ["path", "old_string", "new_string"],
    ),
    _schema(
        "run_command",
        "Run a shell command in the project's folder. Asks the user for permission.",
        {"command": STRING},
        ["command"],
    ),
    _schema(
        "git_status",
        "Show which files changed since the last commit, and the current branch.",
        {},
        [],
    ),
    _schema(
        "git_diff",
        "Show the changes not committed yet, line by line, like `git diff`.",
        {
            "path": {**STRING, "description": "File or folder to limit the diff to. Default: '.'"},
            "staged": {"type": "boolean", "description": "Only the staged changes."},
        },
        [],
    ),
    _schema(
        "git_log",
        "List the last commits of the current branch.",
        {"limit": {**INTEGER, "description": "How many commits (10 by default, 50 at most)."}},
        [],
    ),
    _schema(
        "git_commit",
        "Commit every change of the project (new files included) with a message. "
        "Asks the user for permission, showing them the changes.",
        {"message": {**STRING, "description": "Short summary of what changed and why."}},
        ["message"],
    ),
    _schema(
        ASK_USER,
        "Ask the user a question when a decision is theirs to make, or when you need a "
        "detail you cannot find in the project, then wait for the answer. Offer 2 to 4 "
        "short options; the user may also type another answer.",
        {
            "question": STRING,
            "options": {
                "type": "array",
                "items": STRING,
                "description": "2 to 4 short answers to choose from.",
            },
        },
        ["question", "options"],
    ),
]


class Toolbox:
    """Les outils d'un projet donné : son dossier, et ceux que l'utilisateur ouvre en plus."""

    # Ceux qui modifient quelque chose : ils demandent l'accord de l'utilisateur.
    APPROVAL_NEEDED = frozenset({"write_file", "edit_file", "run_command", "git_commit"})
    # Une commande peut tout lire (cat ~/.ssh/id_rsa) : jamais d'accord pour la suite.
    ASK_EVERY_TIME = frozenset({"run_command"})

    def __init__(
        self,
        folder: Path,
        *,
        reach: Path | None = None,
        max_output_chars: int = 8000,
        max_entries: int = 400,
        command_timeout: int = 120,
        allow_commands: bool = True,
    ) -> None:
        # Le dossier du projet : Git et les chemins relatifs partent de là.
        self._files = Workspace(folder)
        # Le dossier atteignable (votre dossier personnel), au-delà duquel aucun accord ne
        # mène. Sans lui, c'est le projet seul : rien ne peut en sortir.
        reach = (reach or folder).expanduser().resolve()
        self._reach = reach if self._files.root.is_relative_to(reach) else self._files.root
        # Les dossiers ouverts pour l'appel en cours : le projet, et ceux qu'on a autorisés.
        self._roots: tuple[Path, ...] = (self._files.root,)
        self._max_output = max_output_chars
        self._max_entries = max_entries
        self._command_timeout = command_timeout
        self._allow_commands = allow_commands
        self._git = is_git_repository(self._files.root)

    @property
    def folder(self) -> Path:
        return self._files.root

    @property
    def reach(self) -> Path:
        return self._reach

    @property
    def schemas(self) -> list[dict[str, Any]]:
        """Les outils proposés au modèle : sans run_command si les commandes sont coupées, sans
        ceux de Git hors d'un dépôt."""
        hidden = (set() if self._allow_commands else {"run_command"}) | (
            set() if self._git else GIT_TOOLS
        )
        return [schema for schema in SCHEMAS if schema["function"]["name"] not in hidden]

    def asks_every_time(self, name: str) -> bool:
        return name in self.ASK_EVERY_TIME

    def needs_approval(self, name: str) -> bool:
        # Un outil indisponible est refusé d'office : inutile de déranger l'utilisateur.
        return name in self.APPROVAL_NEEDED and name in self._available()

    def _available(self) -> set[str]:
        return {schema["function"]["name"] for schema in self.schemas}

    def access(
        self, name: str, arguments: dict[str, Any], granted: Iterable[Path] = ()
    ) -> Access | None:
        """L'accord que demande ce chemin, en plus de celui de l'outil ; None s'il n'en faut pas.

        Il en faut un hors du projet et des dossiers déjà autorisés (`granted`), et pour tout
        fichier de secrets. Un chemin invalide ou hors d'atteinte ne demande rien : l'exécution
        le refusera, avec son explication.
        """
        if name == "git_commit" and name in self._available():
            # git add --all embarquerait un .env que le .gitignore oublie : à signaler.
            return Access(folder=None, sensitive=True) if self._commits_a_secret() else None
        path = arguments.get("path", ".")
        if name not in PATH_TOOLS or name not in self._available() or not isinstance(path, str):
            return None
        try:
            target = self._locate(path)
        except ToolError:
            return None
        sensitive = is_sensitive(target, self._reach)
        inside = any(target.is_relative_to(root) for root in (self.folder, *granted))
        if inside and not sensitive:
            return None
        return Access(folder=None if inside else self._folder_to_open(target), sensitive=sensitive)

    def _folder_to_open(self, target: Path) -> Path:
        """Le dossier à autoriser pour atteindre `target` : son dépôt Git s'il est dans l'un
        (on y travaille rarement sur un seul fichier), sinon le dossier qui le contient.

        Jamais le dossier atteignable lui-même, sauf pour un chemin qui y mène directement
        (~ ou ~/.bashrc) : il ouvrirait tout, et l'accord ne vaut alors que cette fois.
        """
        folder = target if target.is_dir() else target.parent
        while not folder.exists() and folder != self._reach:
            folder = folder.parent  # un fichier à créer dans un dossier qui n'existe pas encore
        for candidate in (folder, *folder.parents):
            if candidate == self._reach or not candidate.is_relative_to(self._reach):
                break
            if (candidate / ".git").exists():
                return candidate
        if folder == self._reach and target.parent != self._reach and target != self._reach:
            # ~/notes/2026/idees.md, notes n'existant pas encore : on ouvre ~/notes.
            return self._reach / target.relative_to(self._reach).parts[0]
        return folder

    def describe(self, name: str, arguments: dict[str, Any]) -> str:
        """Résumé court d'un appel, affiché dans l'interface : `read_file(src/api.ts)`."""
        if name == "run_command":
            detail = str(arguments.get("command", ""))
        else:
            detail = str(
                arguments.get("path")
                or arguments.get("pattern")
                or arguments.get("question")
                or arguments.get("message")
                or ""
            )
        if len(detail) > 120:
            detail = detail[:117] + "…"
        return f"{name}({detail})"

    async def preview(self, name: str, arguments: dict[str, Any]) -> list[FileDiff]:
        """Ce que l'action changerait, fichier par fichier, sans rien écrire : à relire avant
        d'autoriser. Un fichier pour write_file et edit_file, tous ceux du commit pour git_commit.

        Vide pour les autres outils, et pour un appel voué à l'échec (fichier introuvable,
        extrait absent) : l'erreur viendra de l'exécution, avec son explication.
        """
        return await anyio.to_thread.run_sync(lambda: self._preview(name, arguments))

    def _with_roots(self, roots: tuple[Path, ...], action: Callable[[], T]) -> T:
        previous, self._roots = self._roots, roots
        try:
            return action()
        finally:
            self._roots = previous

    def _preview(self, name: str, arguments: dict[str, Any]) -> list[FileDiff]:
        # L'aperçu ne part qu'à l'utilisateur, jamais au modèle : il peut lire tout le dossier
        # atteignable, pour montrer ce qu'une écriture hors du projet changerait.
        return self._with_roots((self._reach,), lambda: self._previews(name, arguments))

    def _previews(self, name: str, arguments: dict[str, Any]) -> list[FileDiff]:
        if name == "git_commit":
            try:
                return self._pending_changes() if self._git else []
            except ToolError, WorkspaceError, OSError:
                return []
        diff = self._file_preview(name, arguments)
        return [diff] if diff else []

    def _commits_a_secret(self) -> bool:
        try:
            changed = self._run_git("status", "--porcelain", "-z", "--untracked-files=all")
        except ToolError:
            return False
        # -z : « XY chemin », puis l'ancien nom après un renommage, qu'on vérifie aussi.
        paths = [entry[3:] if entry[2:3] == " " else entry for entry in changed.split("\0")]
        return any(self._is_secret(path) for path in paths if path)

    def _is_secret(self, path: str) -> bool:
        return is_sensitive(self._files.root / path, self._reach)

    def _pending_changes(self) -> list[FileDiff]:
        """Ce qu'un commit de tout le projet enregistrerait : fichiers suivis, puis nouveaux.
        Un fichier de secrets y figure, sans son contenu."""
        has_head = self._git_quiet("rev-parse", "--verify", "--quiet", "HEAD")
        diffs = [
            diff.model_copy(update={"lines": []}) if self._is_secret(diff.path) else diff
            for diff in parse_diff(
                self._run_git(
                    "diff", "HEAD" if has_head else "--cached", "--no-color", "--no-ext-diff"
                )
            )
        ]
        untracked = self._run_git("ls-files", "--others", "--exclude-standard", "-z")
        for path in [path for path in untracked.split("\0") if path]:
            if len(diffs) >= MAX_PREVIEW_FILES:
                break
            diffs.append(self._new_file_diff(path))
        return diffs[:MAX_PREVIEW_FILES]

    def _new_file_diff(self, path: str) -> FileDiff:
        # resolve() : un lien symbolique non suivi par Git ne doit pas faire lire l'extérieur.
        file = self._files.resolve(path)
        empty = FileDiff(path=path, created=True, added=0, removed=0, lines=[])
        if self._is_secret(path):
            return empty
        try:
            if file.stat().st_size > MAX_PREVIEW_BYTES:
                return empty
            return make_diff(path, "", file.read_text(encoding="utf-8"), created=True)
        except OSError, UnicodeDecodeError:
            return empty  # binaire ou illisible : il sera commité, sans aperçu

    def _file_preview(self, name: str, arguments: dict[str, Any]) -> FileDiff | None:
        path = arguments.get("path")
        if name not in ("write_file", "edit_file") or not isinstance(path, str):
            return None
        try:
            if name == "write_file":
                new = arguments.get("content")
                file = self._resolve(path)
                created = not file.exists()
                if not isinstance(new, str) or file.is_dir():
                    return None
                return make_diff(path, "" if created else self._text(file), new, created=created)

            old_string, new_string = arguments.get("old_string"), arguments.get("new_string")
            if not isinstance(old_string, str) or not isinstance(new_string, str):
                return None
            text = self._text(self._file(path))
            if text.count(old_string) != 1:
                return None
            return make_diff(path, text, text.replace(old_string, new_string))
        except ToolError, WorkspaceError, OSError:
            return None

    async def run(
        self, name: str, arguments: dict[str, Any], roots: Iterable[Path] = ()
    ) -> ToolResult:
        """Exécute l'outil dans un thread : lire un dossier ou lancer une commande bloque.

        `roots` : les dossiers hors du projet que l'utilisateur a ouverts pour cet appel.
        """
        roots = tuple(roots)

        def run() -> ToolResult:
            opened = (self._files.root, *(Path(root).resolve() for root in roots))
            return self._with_roots(opened, lambda: self._run(name, arguments))

        return await anyio.to_thread.run_sync(run)

    def _run(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        if name == "run_command" and not self._allow_commands:
            return ToolResult("Commands are turned off on this server.", error=True)
        # Un outil que le modèle ne s'est pas vu proposer reste inconnu, même s'il en devine
        # le nom : c'est la liste des schémas qui fait foi.
        handler = getattr(self, f"_{name}", None) if name in self._available() else None
        if handler is None:
            return ToolResult(f"Unknown tool: {name}", error=True)
        try:
            return ToolResult(self._truncate(handler(**arguments)))
        except (ToolError, WorkspaceError) as exc:
            return ToolResult(str(exc), error=True)
        except TypeError as exc:
            # Le modèle a inventé des arguments : on le lui dit plutôt que de planter.
            return ToolResult(f"Bad arguments for {name}: {exc}", error=True)
        except OSError as exc:
            return ToolResult(f"{type(exc).__name__}: {exc.strerror or exc}", error=True)

    # --- Les outils eux-mêmes ---

    def _list_files(self, path: str = ".") -> str:
        lines: list[str] = []
        for entry in self._walk(self._directory(path)):
            if len(lines) >= self._max_entries:
                lines.append(f"… (stopped at {self._max_entries} entries)")
                break
            lines.append(entry)
        return "\n".join(lines) or "(empty folder)"

    def _read_file(self, path: str, offset: int = 1, limit: int = 400) -> str:
        lines = self._text(self._file(path)).splitlines()
        start = max(offset, 1) - 1
        shown = lines[start : start + max(limit, 1)]
        if not shown:
            return f"(no line {offset}: the file has {len(lines)} lines)"
        numbered = "\n".join(f"{start + i + 1:>5}  {line}" for i, line in enumerate(shown))
        remaining = len(lines) - (start + len(shown))
        if remaining > 0:
            numbered += (
                f"\n… {remaining} more lines (read them with offset={start + len(shown) + 1})"
            )
        return numbered

    def _search_files(self, pattern: str, path: str = ".") -> str:
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            raise ToolError(f"Invalid regular expression: {exc}") from exc

        hits: list[str] = []
        for child, entry in self._entries(self._directory(path)):
            if entry.endswith("/"):
                continue
            try:
                text = child.read_text(encoding="utf-8")
            except OSError, UnicodeDecodeError:
                continue  # fichier binaire ou illisible : on passe
            for number, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    hits.append(f"{entry}:{number}: {line.strip()[:200]}")
                    if len(hits) >= 50:
                        return "\n".join(hits) + "\n… (more matches, narrow the search)"
        return "\n".join(hits) or "No match."

    def _write_file(self, path: str, content: str) -> str:
        file = self._resolve(path)
        if file.is_dir():
            raise ToolError(f"{path} is a folder")
        file.parent.mkdir(parents=True, exist_ok=True)
        existed = file.exists()
        file.write_text(content, encoding="utf-8")
        return f"{'Updated' if existed else 'Created'} {path} ({len(content.splitlines())} lines)"

    def _edit_file(self, path: str, old_string: str, new_string: str) -> str:
        file = self._file(path)
        text = self._text(file)
        found = text.count(old_string)
        if found == 0:
            raise ToolError(f"old_string was not found in {path}")
        if found > 1:
            raise ToolError(f"old_string appears {found} times in {path}: make it unique")
        file.write_text(text.replace(old_string, new_string), encoding="utf-8")
        return f"Edited {path}"

    def _git_status(self) -> str:
        return self._run_git("status", "--short", "--branch").strip()

    def _git_diff(self, path: str = ".", staged: bool = False) -> str:
        # Le chemin passe par la même garde que les autres outils, puis après « -- » : Git ne
        # peut pas le prendre pour une option.
        target = self._files.relative(self._files.resolve(path)) or "."
        arguments = ["diff", "--no-color", "--no-ext-diff"]
        if staged:
            arguments.append("--staged")
        # Le contenu d'un fichier de secrets n'arrive jamais au modèle, même suivi par Git.
        # --relative : des noms relatifs au projet, même s'il n'est qu'un sous-dossier du dépôt.
        listed = self._run_git(*arguments, "--name-only", "--relative", "-z", "--", target)
        changed = [name for name in listed.split("\0") if name]
        secrets = [name for name in changed if self._is_secret(name)]
        kept = [f":(literal){name}" for name in changed if name not in secrets]
        diff = self._run_git(*arguments, "--", *kept).strip() if kept else ""
        if secrets:
            diff += f"\n(secret files left out: {', '.join(secrets)})"
        return diff.strip() or "No changes."

    def _git_log(self, limit: int = 10) -> str:
        count = max(1, min(limit, 50)) if isinstance(limit, int) else 10
        try:
            return self._run_git("log", "--oneline", "--decorate", f"-n{count}").strip()
        except ToolError as exc:
            if "does not have any commits" in str(exc):
                return "No commits yet."
            raise

    def _git_commit(self, message: str) -> str:
        if not isinstance(message, str) or not message.strip():
            raise ToolError("A commit needs a message")
        self._run_git("add", "--all")
        if not self._run_git("diff", "--cached", "--name-only").strip():
            raise ToolError("Nothing to commit: no file changed since the last commit")
        self._run_git("commit", "--quiet", "-m", message.strip())
        return self._run_git("show", "--stat", "--format=Committed %h: %s", "HEAD").strip()

    def _run_git(self, *arguments: str) -> str:
        try:
            return run_git(self._files.root, *arguments, timeout=self._command_timeout)
        except GitError as exc:
            raise ToolError(str(exc)) from exc

    def _git_quiet(self, *arguments: str) -> bool:
        """Vrai si la commande réussit (pour un test, comme « y a-t-il un commit ? »)."""
        try:
            self._run_git(*arguments)
        except ToolError:
            return False
        return True

    def _run_command(self, command: str) -> str:
        try:
            # shell=True : c'est le but de l'outil, et l'utilisateur a validé la commande.
            done = subprocess.run(  # noqa: S602
                command,
                shell=True,
                cwd=self._files.root,
                env=command_environment(os.environ),
                capture_output=True,
                text=True,
                timeout=self._command_timeout,
            )
        except subprocess.TimeoutExpired:
            raise ToolError(f"Command stopped after {self._command_timeout}s") from None
        output = (done.stdout + done.stderr).strip() or "(no output)"
        return f"exit code {done.returncode}\n{output}"

    # --- Outillage interne ---

    def _walk(self, folder: Path) -> Iterator[str]:
        return (entry for _, entry in self._entries(folder))

    def _entries(self, folder: Path, seen: set[Path] | None = None) -> Iterator[tuple[Path, str]]:
        """(chemin, nom affiché) des fichiers du dossier, en profondeur, sans les dossiers
        cachés, les IGNORED ni les secrets : lister ou fouiller ne les lit jamais."""
        # Les dossiers déjà parcourus : un lien qui pointe vers un parent tournerait sans fin.
        seen = seen if seen is not None else {folder.resolve()}
        try:
            children = sorted(folder.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower()))
        except OSError:
            return
        for child in children:
            if child.name.startswith(".") or child.name in IGNORED:
                continue
            if is_sensitive(child.resolve(), self._reach):
                continue
            shown = self._display(child)
            if child.is_dir():
                real = child.resolve()
                if real in seen or (child.is_symlink() and not self._is_open(real)):
                    continue  # un lien vers un dossier fermé, ou déjà vu : on ne le suit pas
                seen.add(real)
                yield child, f"{shown}/"
                yield from self._entries(child, seen)
            elif child.is_file() and self._is_open(child.resolve()):
                yield child, shown

    def _display(self, path: Path) -> str:
        """Relatif au projet quand il y est, absolu sinon : réutilisable tel quel par le modèle."""
        if path.is_relative_to(self._files.root):
            return path.relative_to(self._files.root).as_posix()
        return path.as_posix()

    def _locate(self, path: str) -> Path:
        """Le chemin résolu, relatif au projet ou absolu (« ~ » : le dossier atteignable),
        garanti dans le dossier atteignable, mais pas forcément ouvert."""
        if path == "~" or path.startswith("~/"):
            candidate = self._reach / path[2:]
        else:
            candidate = self._files.root / path  # un chemin absolu remplace la racine
        try:
            resolved = candidate.resolve()
        except (OSError, RuntimeError) as exc:
            raise ToolError(f"Cannot resolve {path}: {exc}") from exc
        if not resolved.is_relative_to(self._reach):
            raise ToolError(f"{path} is outside the folders the agent can reach")
        return resolved

    def _resolve(self, path: str) -> Path:
        """Comme `_locate`, mais le chemin doit être dans un dossier ouvert pour cet appel."""
        resolved = self._locate(path)
        if not self._is_open(resolved):
            raise ToolError(f"{path} is outside the project, and the user has not opened it")
        return resolved

    def _is_open(self, path: Path) -> bool:
        return any(path.is_relative_to(root) for root in self._roots)

    def _file(self, path: str) -> Path:
        file = self._resolve(path)
        if not file.is_file():
            raise ToolError(f"File not found: {path}")
        return file

    def _directory(self, path: str) -> Path:
        folder = self._resolve(path or ".")
        if not folder.is_dir():
            raise ToolError(f"Folder not found: {path}")
        return folder

    def _text(self, file: Path) -> str:
        try:
            return file.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ToolError(f"{file.name} is not a text file") from exc

    def _truncate(self, output: str) -> str:
        if len(output) <= self._max_output:
            return output
        return output[: self._max_output] + f"\n… (truncated at {self._max_output} characters)"
