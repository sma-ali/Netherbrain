"""L'accès hors du projet : un dossier n'est ouvert qu'avec l'accord de l'utilisateur, et un
fichier de secrets le redemande à chaque fois."""

import asyncio
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from conftest import FakeProvider
from test_agent import (
    ask,
    decide,
    event_of,
    make_project,
    names,
    tool_call,
    wait_for_request,
)

from netherbrain.agent.tools import Access, Toolbox
from netherbrain.projects.workspace import Workspace, is_sensitive, locate_project
from netherbrain.schemas import TokenEvent


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """Un dossier personnel : un projet, un autre dépôt à côté, et des secrets."""
    (tmp_path / "projet").mkdir()
    (tmp_path / "projet" / "app.py").write_text("x = 1\n")
    (tmp_path / "projet" / ".env").write_text("CLE=secrete\n")
    (tmp_path / "heretic" / ".git").mkdir(parents=True)
    (tmp_path / "heretic" / "src").mkdir()
    (tmp_path / "heretic" / "src" / "main.py").write_text("print('heretic')\n")
    (tmp_path / ".config" / "cles").mkdir(parents=True)
    (tmp_path / ".config" / "cles" / "tmdb.env").write_text("TMDB=secrete\n")
    return tmp_path.resolve()


def wait_for_call(approvals, conversation_id: str, call_id: str) -> str:
    """Attend la demande de cet appel précis : la précédente peut traîner un instant."""
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if call_id in approvals.pending_calls(uuid.UUID(conversation_id)):
            return call_id
        time.sleep(0.02)
    raise AssertionError(f"aucune demande pour {call_id}")


def toolbox(home: Path) -> Toolbox:
    return Toolbox(home / "projet", reach=home)


def run(box: Toolbox, name: str, roots=(), **arguments) -> str:
    return asyncio.run(box.run(name, arguments, roots)).output


# --- Ce que chaque chemin demande ---


def test_the_project_is_open_without_asking(home):
    assert toolbox(home).access("read_file", {"path": "app.py"}) is None


def test_another_repository_asks_to_open_its_root(home):
    access = toolbox(home).access("read_file", {"path": "~/heretic/src/main.py"})

    # Le dépôt entier, pas seulement src/ : on travaille rarement sur un seul fichier.
    assert access == Access(folder=home / "heretic", sensitive=False)


def test_a_folder_already_opened_asks_nothing(home):
    box = toolbox(home)
    path = {"path": str(home / "heretic" / "src" / "main.py")}

    assert box.access("read_file", path, granted=[home / "heretic"]) is None


def test_a_new_file_in_a_missing_folder_opens_its_closest_parent(home):
    access = toolbox(home).access("write_file", {"path": "~/notes/2026/idees.md", "content": ""})

    # ~/notes, pas le dossier personnel entier.
    assert access == Access(folder=home / "notes", sensitive=False)


def test_a_git_folder_at_home_does_not_open_everything(home):
    (home / ".git").mkdir()

    access = toolbox(home).access("read_file", {"path": "~/notes/idees.md"})

    assert access == Access(folder=home / "notes", sensitive=False)


@pytest.mark.parametrize(
    "name",
    [".npmrc", "id_ed25519", "server.PEM", ".bashrc", ".ENV", ".claude/.credentials.json"],
)
def test_more_secrets(home, name):
    assert is_sensitive(home / name, home)


def test_git_hooks_and_public_keys(home):
    assert is_sensitive(home / "projet" / ".git" / "hooks" / "pre-commit", home)
    assert not is_sensitive(home / ".pubkeys" / "id_ed25519.pub", home)


@pytest.mark.parametrize("path", [".env", "~/.config/cles/tmdb.env"])
def test_secrets_always_ask(home, path):
    access = toolbox(home).access("read_file", {"path": path}, granted=[home / ".config"])

    assert access is not None and access.sensitive


def test_an_env_template_is_not_a_secret(home):
    assert not is_sensitive(home / "projet" / ".env.example", home)
    assert is_sensitive(home / "projet" / ".env.local", home)


def test_tools_without_a_path_ask_nothing_more(home):
    assert toolbox(home).access("run_command", {"command": "cat ~/heretic/src/main.py"}) is None


# --- Ce que l'exécution laisse passer ---


def test_a_folder_not_opened_is_refused(home):
    output = run(toolbox(home), "read_file", path="~/heretic/src/main.py")

    assert "has not opened it" in output


def test_an_opened_folder_can_be_read(home):
    output = run(toolbox(home), "read_file", [home / "heretic"], path="~/heretic/src/main.py")

    assert "print('heretic')" in output


def test_nothing_beyond_the_home_folder(home):
    box = toolbox(home)

    assert "outside the folders" in run(box, "read_file", [home], path="/etc/hostname")
    assert "outside the folders" in run(box, "read_file", [home], path="../../x")


def test_a_symlink_cannot_open_a_closed_folder(home):
    (home / "projet" / "raccourci").symlink_to(home / "heretic")

    output = run(toolbox(home), "read_file", path="raccourci/src/main.py")

    assert "has not opened it" in output


def test_listing_and_searching_never_read_secrets(home):
    box = toolbox(home)

    listing = run(box, "list_files", [home / ".config"], path="~/.config")
    found = run(box, "search_files", [home / ".config"], pattern="secrete", path="~/.config")

    assert "tmdb.env" not in listing
    assert found == "No match."


def test_a_symlink_loop_is_listed_once(home):
    (home / "heretic" / "src" / "boucle").symlink_to(home / "heretic")

    listing = run(toolbox(home), "list_files", [home / "heretic"], path="~/heretic")

    assert listing.count("main.py") == 1


def git(folder: Path, *arguments: str) -> None:
    subprocess.run(["git", "-C", str(folder), *arguments], check=True, capture_output=True)


@pytest.fixture
def repository(home: Path) -> Path:
    folder = home / "projet"
    git(folder, "init", "-q")
    git(
        folder,
        "-c",
        "user.email=a@b",
        "-c",
        "user.name=a",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "x",
    )
    return folder


def test_a_commit_carrying_a_secret_is_flagged(home, repository):
    box = toolbox(home)

    assert box.access("git_commit", {"message": "x"}) == Access(folder=None, sensitive=True)
    # Le fichier figure dans l'aperçu, sans son contenu.
    preview = {diff.path: diff for diff in box._preview("git_commit", {"message": "x"})}
    assert preview[".env"].lines == []
    assert preview["app.py"].lines


def test_a_clean_commit_asks_nothing_more(home, repository):
    (repository / ".gitignore").write_text(".env\n")

    assert toolbox(home).access("git_commit", {"message": "x"}) is None


def test_git_diff_leaves_secrets_out(home, repository):
    git(repository, "add", "--all")
    git(repository, "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "-m", "y")
    (repository / ".env").write_text("CLE=nouvelle\n")
    (repository / "app.py").write_text("x = 2\n")

    output = run(toolbox(home), "git_diff")

    assert "x = 2" in output
    assert "nouvelle" not in output
    assert "secret files left out: .env" in output


def test_paths_outside_the_project_are_shown_in_full(home):
    listing = run(toolbox(home), "list_files", [home / "heretic"], path="~/heretic")

    assert f"{home}/heretic/src/main.py" in listing.splitlines()


# --- Les projets ---


def test_an_old_project_is_found_in_the_old_workspace(home):
    reach, legacy = Workspace(home), Workspace(home / "projet")

    assert locate_project(".", reach, legacy) == home / "projet"
    assert locate_project(str(home / "heretic"), reach, legacy) == home / "heretic"
    # Un chemin absolu hors du dossier atteignable n'est plus un dossier de projet.
    assert locate_project("/etc", reach, legacy) is None


def test_a_project_can_be_any_folder_of_the_home_folder(client, workspace):
    (workspace / "Projects" / "heretic").mkdir(parents=True)

    response = client.post("/api/projects", json={"path": "Projects/heretic"})

    assert response.status_code == 201
    assert response.json()["path"] == str((workspace / "Projects" / "heretic").resolve())
    # Le dossier personnel entier ouvrirait tout à la lecture, sans accord.
    assert client.post("/api/projects", json={"path": ""}).status_code == 400


# --- La boucle de l'agent ---


def outside_read(workspace: Path, call_id: str) -> object:
    path = workspace / "heretic" / "main.py"
    return tool_call("read_file", f'{{"path": "{path}"}}', call_id=call_id)


@pytest.fixture
def heretic(workspace: Path) -> Path:
    (workspace / "heretic").mkdir()
    (workspace / "heretic" / "main.py").write_text("print('heretic')\n")
    return workspace.resolve() / "heretic"


def test_reading_another_folder_asks_first(client, workspace, heretic, use_providers, approvals):
    use_providers(
        FakeProvider(turns=[[outside_read(workspace, "c1")], [TokenEvent(content="Lu.")]])
    )
    conversation_id, _ = make_project(client, workspace, {"app.py": "x = 1\n"})

    with ThreadPoolExecutor(1) as pool:
        streaming = pool.submit(ask, client, conversation_id)
        decide(client, conversation_id, wait_for_request(approvals, conversation_id), "once")
        response = streaming.result(timeout=10)

    assert event_of(response, "tool_request")["folder"] == str(heretic)
    assert "print('heretic')" in event_of(response, "tool_result")["output"]


def test_opening_a_folder_for_the_conversation(
    client, workspace, heretic, use_providers, approvals
):
    use_providers(
        FakeProvider(
            turns=[
                [outside_read(workspace, "c1")],
                [outside_read(workspace, "c2")],
                [TokenEvent(content="Lu deux fois.")],
            ]
        )
    )
    conversation_id, _ = make_project(client, workspace, {"app.py": "x = 1\n"})

    with ThreadPoolExecutor(1) as pool:
        streaming = pool.submit(ask, client, conversation_id)
        decide(client, conversation_id, wait_for_request(approvals, conversation_id), "always")
        response = streaming.result(timeout=10)

    # Le second appel ne redemande rien : le dossier est ouvert pour toute la conversation.
    assert names(response).count("tool_request") == 1


def test_a_secret_asks_again_even_after_always(client, workspace, use_providers, approvals):
    read_env = '{"path": ".env"}'
    use_providers(
        FakeProvider(
            turns=[
                [tool_call("read_file", read_env, call_id="c1")],
                [tool_call("read_file", read_env, call_id="c2")],
                [TokenEvent(content="Fini.")],
            ]
        )
    )
    conversation_id, _ = make_project(client, workspace, {".env": "CLE=1\n"})

    with ThreadPoolExecutor(1) as pool:
        streaming = pool.submit(ask, client, conversation_id)
        decide(client, conversation_id, wait_for_call(approvals, conversation_id, "c1"), "always")
        decide(client, conversation_id, wait_for_call(approvals, conversation_id, "c2"), "deny")
        response = streaming.result(timeout=10)

    assert names(response).count("tool_request") == 2
    assert event_of(response, "tool_request")["sensitive"] is True


def test_a_command_is_never_allowed_for_good(client, workspace, use_providers, approvals):
    echo = '{"command": "echo un"}'
    use_providers(
        FakeProvider(
            turns=[
                [tool_call("run_command", echo, call_id="c1")],
                [tool_call("run_command", echo, call_id="c2")],
                [TokenEvent(content="Fini.")],
            ]
        )
    )
    conversation_id, _ = make_project(client, workspace, {"app.py": "x = 1\n"})

    with ThreadPoolExecutor(1) as pool:
        streaming = pool.submit(ask, client, conversation_id)
        decide(client, conversation_id, wait_for_call(approvals, conversation_id, "c1"), "always")
        decide(client, conversation_id, wait_for_call(approvals, conversation_id, "c2"), "deny")
        response = streaming.result(timeout=10)

    # Une commande peut lire n'importe quel secret : elle se redemande à chaque fois.
    assert names(response).count("tool_request") == 2
    assert event_of(response, "tool_request")["once_only"] is True


def test_opening_a_folder_does_not_allow_writing_in_it(
    client, workspace, heretic, use_providers, approvals
):
    write = tool_call("write_file", f'{{"path": "{heretic}/b.txt", "content": "2"}}', call_id="c2")
    use_providers(
        FakeProvider(turns=[[outside_read(workspace, "c1")], [write], [TokenEvent(content="Ok.")]])
    )
    conversation_id, _ = make_project(client, workspace, {"app.py": "x = 1\n"})

    with ThreadPoolExecutor(1) as pool:
        streaming = pool.submit(ask, client, conversation_id)
        decide(client, conversation_id, wait_for_call(approvals, conversation_id, "c1"), "always")
        # Le dossier est ouvert, mais une écriture reste soumise à l'accord de l'outil.
        decide(client, conversation_id, wait_for_call(approvals, conversation_id, "c2"), "deny")
        response = streaming.result(timeout=10)

    assert names(response).count("tool_request") == 2
    assert not (heretic / "b.txt").exists()
