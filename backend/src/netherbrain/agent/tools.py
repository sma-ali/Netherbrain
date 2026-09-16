"""Les outils que le modèle peut demander : lister, lire, chercher, écrire, exécuter.

Tous les chemins sont confinés au dossier du projet par `Workspace`, la même garde que
pour le navigateur de dossiers : ni « .. », ni chemin absolu, ni lien symbolique n'en sort.
"""

import os
import re
import subprocess
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anyio

from netherbrain.agent.diff import make_diff
from netherbrain.projects.workspace import Workspace, WorkspaceError
from netherbrain.schemas import FileDiff

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


# Les seules variables d'environnement transmises aux commandes : de quoi trouver les
# programmes et afficher du texte, rien de plus. Une liste de ce qui est permis plutôt que de
# ce qui est interdit : une clé d'API ajoutée demain restera cachée sans y penser.
COMMAND_ENVIRONMENT = frozenset(
    {"PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LANGUAGE", "TERM", "TZ", "TMPDIR"}
)


def command_environment(environ: Mapping[str, str]) -> dict[str, str]:
    """L'environnement d'une commande de l'agent, sans les secrets du serveur."""
    return {
        name: value
        for name, value in environ.items()
        if name in COMMAND_ENVIRONMENT or name.startswith("LC_")
    }


class ToolError(Exception):
    """Un outil n'a pas pu faire ce qu'on lui demandait ; le message part au modèle."""


@dataclass
class ToolResult:
    output: str
    error: bool = False


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

# Un outil à part : il n'agit pas sur les fichiers, il pose une question à l'utilisateur,
# qui répond en cliquant sur l'une des propositions (ou en écrivant sa propre réponse).
ASK_USER = "ask_user"

SCHEMAS = [
    _schema(
        "list_files",
        "List the files and folders of the project, recursively.",
        {"path": {**STRING, "description": "Folder, relative to the project root. Default: '.'"}},
        [],
    ),
    _schema(
        "read_file",
        "Read a text file of the project. The answer is numbered, like `cat -n`.",
        {
            "path": {**STRING, "description": "File, relative to the project root."},
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
            "path": {**STRING, "description": "Folder to search in. Default: '.'"},
        },
        ["pattern"],
    ),
    _schema(
        "write_file",
        "Create a file or replace its whole content. Asks the user for permission.",
        {"path": STRING, "content": STRING},
        ["path", "content"],
    ),
    _schema(
        "edit_file",
        "Replace one exact excerpt of a file, which must appear exactly once. "
        "Asks the user for permission.",
        {"path": STRING, "old_string": STRING, "new_string": STRING},
        ["path", "old_string", "new_string"],
    ),
    _schema(
        "run_command",
        "Run a shell command in the project's folder. Asks the user for permission.",
        {"command": STRING},
        ["command"],
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
    """Les outils d'un projet donné, tous confinés à son dossier."""

    # Ceux qui modifient quelque chose : ils demandent l'accord de l'utilisateur.
    APPROVAL_NEEDED = frozenset({"write_file", "edit_file", "run_command"})

    def __init__(
        self,
        folder: Path,
        *,
        max_output_chars: int = 8000,
        max_entries: int = 400,
        command_timeout: int = 120,
        allow_commands: bool = True,
    ) -> None:
        # Le dossier du projet devient la racine : la même classe qui empêche de sortir
        # du dossier de travail empêche ici de sortir du projet.
        self._files = Workspace(folder)
        self._max_output = max_output_chars
        self._max_entries = max_entries
        self._command_timeout = command_timeout
        self._allow_commands = allow_commands

    @property
    def folder(self) -> Path:
        return self._files.root

    @property
    def schemas(self) -> list[dict[str, Any]]:
        """Les outils proposés au modèle : sans run_command si les commandes sont coupées."""
        if self._allow_commands:
            return SCHEMAS
        return [schema for schema in SCHEMAS if schema["function"]["name"] != "run_command"]

    def needs_approval(self, name: str) -> bool:
        # Un outil indisponible est refusé d'office : inutile de déranger l'utilisateur.
        return name in self.APPROVAL_NEEDED and name in self._available()

    def _available(self) -> set[str]:
        return {schema["function"]["name"] for schema in self.schemas}

    def describe(self, name: str, arguments: dict[str, Any]) -> str:
        """Résumé court d'un appel, affiché dans l'interface : `read_file(src/api.ts)`."""
        if name == "run_command":
            detail = str(arguments.get("command", ""))
        else:
            detail = str(
                arguments.get("path") or arguments.get("pattern") or arguments.get("question") or ""
            )
        if len(detail) > 120:
            detail = detail[:117] + "…"
        return f"{name}({detail})"

    async def preview(self, name: str, arguments: dict[str, Any]) -> FileDiff | None:
        """Ce que write_file ou edit_file changerait, sans rien écrire : à relire avant d'autoriser.

        None pour les autres outils, et pour un appel voué à l'échec (fichier introuvable,
        extrait absent) : l'erreur viendra de l'exécution, avec son explication.
        """
        return await anyio.to_thread.run_sync(lambda: self._preview(name, arguments))

    def _preview(self, name: str, arguments: dict[str, Any]) -> FileDiff | None:
        path = arguments.get("path")
        if name not in ("write_file", "edit_file") or not isinstance(path, str):
            return None
        try:
            if name == "write_file":
                new = arguments.get("content")
                file = self._files.resolve(path)
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

    async def run(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """Exécute l'outil dans un thread : lire un dossier ou lancer une commande bloque."""
        return await anyio.to_thread.run_sync(lambda: self._run(name, arguments))

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
        for entry in self._walk(self._directory(path)):
            if entry.endswith("/"):
                continue
            try:
                text = (self._files.root / entry).read_text(encoding="utf-8")
            except OSError, UnicodeDecodeError:
                continue  # fichier binaire ou illisible : on passe
            for number, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    hits.append(f"{entry}:{number}: {line.strip()[:200]}")
                    if len(hits) >= 50:
                        return "\n".join(hits) + "\n… (more matches, narrow the search)"
        return "\n".join(hits) or "No match."

    def _write_file(self, path: str, content: str) -> str:
        file = self._files.resolve(path)
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
        """Les chemins du dossier, en profondeur, sans les dossiers cachés ni les IGNORED."""
        try:
            children = sorted(folder.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower()))
        except OSError:
            return
        for child in children:
            if child.name.startswith(".") or child.name in IGNORED:
                continue
            relative = child.relative_to(self._files.root).as_posix()
            if child.is_dir():
                yield f"{relative}/"
                yield from self._walk(child)
            elif child.is_file():
                yield relative

    def _file(self, path: str) -> Path:
        file = self._files.resolve(path)
        if not file.is_file():
            raise ToolError(f"File not found: {path}")
        return file

    def _directory(self, path: str) -> Path:
        return self._files.directory(path or ".")

    def _text(self, file: Path) -> str:
        try:
            return file.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ToolError(f"{file.name} is not a text file") from exc

    def _truncate(self, output: str) -> str:
        if len(output) <= self._max_output:
            return output
        return output[: self._max_output] + f"\n… (truncated at {self._max_output} characters)"
