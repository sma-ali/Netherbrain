"""Les projets : choisir un dossier du dossier de travail, y rattacher des conversations."""

import pytest
from conftest import FakeEmbedder, FakeProvider

from netherbrain.projects.prompt import MAX_ENTRIES, build_project_context
from netherbrain.projects.workspace import Workspace, WorkspaceError, git_branch
from netherbrain.schemas import TokenEvent

MISSING_ID = "01a09034-355e-71a4-8403-8a1b1710aa0f"


def make_repo(folder, branch: str = "main") -> None:
    (folder / ".git").mkdir(parents=True)
    (folder / ".git" / "HEAD").write_text(f"ref: refs/heads/{branch}\n")


def create_project(client, path: str, **fields):
    return client.post("/api/projects", json={"path": path, **fields})


def new_project(client, workspace, folder: str = "nb") -> str:
    (workspace / folder).mkdir(exist_ok=True)
    return create_project(client, folder).json()["id"]


def new_conversation(client, project_id: str | None = None) -> str:
    return client.post("/api/conversations", json={"project_id": project_id}).json()["id"]


def send(client, conversation_id: str, content: str = "Salut", **fields):
    return client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"provider": "fake", "model": "fake-model", "content": content, **fields},
    )


def list_folders(client, path: str = ""):
    return client.get("/api/workspace/directories", params={"path": path})


# --- Parcourir le dossier de travail ---


def test_folders_are_listed_without_hidden_ones(client, workspace):
    (workspace / "beta").mkdir()
    (workspace / "Alpha").mkdir()
    (workspace / ".cache").mkdir()
    (workspace / "notes.txt").write_text("pas un dossier")
    make_repo(workspace / "beta")

    listing = list_folders(client).json()

    assert (listing["path"], listing["parent"]) == ("", None)
    assert [(d["name"], d["is_git"]) for d in listing["directories"]] == [
        ("Alpha", False),
        ("beta", True),
    ]


def test_a_subfolder_knows_its_parent(client, workspace):
    (workspace / "apps" / "web").mkdir(parents=True)

    listing = list_folders(client, "apps").json()

    assert (listing["path"], listing["parent"]) == ("apps", "")
    assert listing["directories"] == [{"name": "web", "path": "apps/web", "is_git": False}]


@pytest.mark.parametrize("path", ["..", "apps/../..", "/etc"])
def test_paths_cannot_leave_the_workspace(client, workspace, path):
    (workspace / "apps").mkdir()

    assert list_folders(client, path).status_code == 400
    assert create_project(client, path).status_code == 400


def test_symbolic_links_cannot_leave_the_workspace(client, workspace, tmp_path):
    outside = tmp_path / "secrets"
    outside.mkdir()
    (workspace / "link").symlink_to(outside)

    assert list_folders(client).json()["directories"] == []
    assert list_folders(client, "link").status_code == 400
    assert create_project(client, "link").status_code == 400


def test_a_missing_folder_is_404(client, workspace):
    assert list_folders(client, "nope").status_code == 404


def test_resolve_normalizes_paths(tmp_path):
    workspace = Workspace(tmp_path)

    assert workspace.resolve("a/../b") == tmp_path.resolve() / "b"
    with pytest.raises(WorkspaceError):
        workspace.resolve("../b")


# --- Projets ---


def test_a_project_is_created_from_a_folder(client, workspace):
    folder = workspace / "netherbrain"
    folder.mkdir()
    (workspace / "apps").mkdir()
    make_repo(folder, "feat/projets")
    (folder / "AGENTS.md").write_text("Réponds en français.")

    response = create_project(client, "apps/../netherbrain")

    assert response.status_code == 201
    project = response.json()
    assert (project["name"], project["path"]) == ("netherbrain", "netherbrain")
    assert project["available"] is True
    assert project["git_branch"] == "feat/projets"
    assert project["instructions_file"] == "AGENTS.md"
    assert [p["id"] for p in client.get("/api/projects").json()] == [project["id"]]


def test_projects_are_sorted_by_name_and_can_be_renamed(client, workspace):
    (workspace / "zeta").mkdir()
    (workspace / "nb").mkdir()
    create_project(client, "zeta")
    create_project(client, "nb", name="  Netherbrain  ")

    assert [p["name"] for p in client.get("/api/projects").json()] == ["Netherbrain", "zeta"]


def test_a_folder_belongs_to_a_single_project(client, workspace):
    (workspace / "nb").mkdir()
    create_project(client, "nb")

    assert create_project(client, "nb/").status_code == 409


@pytest.mark.parametrize("path", ["", ".", "nope"])
def test_the_workspace_itself_or_a_missing_folder_is_refused(client, workspace, path):
    assert create_project(client, path).status_code == 400


def test_a_project_whose_folder_disappeared_is_unavailable(client, workspace):
    project_id = new_project(client, workspace, "old")
    (workspace / "old").rmdir()

    project = client.get(f"/api/projects/{project_id}").json()

    assert (project["available"], project["git_branch"]) == (False, None)


def test_an_unknown_project_is_404(client, workspace):
    assert client.get(f"/api/projects/{MISSING_ID}").status_code == 404
    assert client.delete(f"/api/projects/{MISSING_ID}").status_code == 404


# --- Conversations d'un projet ---


def test_a_conversation_can_belong_to_a_project(client, workspace):
    project_id = new_project(client, workspace)

    conversation = client.post("/api/conversations", json={"project_id": project_id}).json()

    assert conversation["project_id"] == project_id
    # Sans corps, comme avant : une simple discussion.
    assert client.post("/api/conversations").json()["project_id"] is None


def test_a_conversation_in_an_unknown_project_is_404(client, workspace):
    response = client.post("/api/conversations", json={"project_id": MISSING_ID})

    assert response.status_code == 404


def test_deleting_a_project_keeps_its_conversations_and_its_folder(client, workspace):
    project_id = new_project(client, workspace)
    conversation_id = new_conversation(client, project_id)

    assert client.delete(f"/api/projects/{project_id}").status_code == 204

    assert client.get("/api/projects").json() == []
    assert client.get(f"/api/conversations/{conversation_id}").json()["project_id"] is None
    assert (workspace / "nb").is_dir()


def test_the_model_knows_the_project(client, workspace, use_providers):
    provider = FakeProvider(events=[TokenEvent(content="ok")])
    use_providers(provider)
    folder = workspace / "nb"
    (folder / "src").mkdir(parents=True)
    (folder / "README.md").write_text("# NB")
    (folder / ".env").write_text("SECRET=1")
    (folder / "AGENTS.md").write_text("Toujours répondre en pirate.")
    conversation_id = new_conversation(client, new_project(client, workspace))

    send(client, conversation_id, "Salut")

    system, user = provider.received
    assert system.role == "system"
    assert '"nb"' in system.content
    assert "src/\nAGENTS.md\nREADME.md" in system.content
    assert "Toujours répondre en pirate." in system.content
    assert ".env" not in system.content
    assert (user.role, user.content) == ("user", "Salut")


def test_the_project_and_the_documents_share_one_system_message(
    client, workspace, use_providers, use_embedder
):
    use_embedder(FakeEmbedder())
    provider = FakeProvider(events=[TokenEvent(content="ok")])
    use_providers(provider)
    client.post(
        "/api/documents",
        files={"file": ("coffre.txt", b"Le code du coffre est licorne.", "text/plain")},
    )
    conversation_id = new_conversation(client, new_project(client, workspace))

    send(client, conversation_id, "Quel est le code du coffre ?", use_documents=True)

    assert [m.role for m in provider.received] == ["system", "user"]
    assert '"nb"' in provider.received[0].content
    assert "licorne" in provider.received[0].content


# --- Ce que le modèle reçoit du projet ---


def test_the_listing_is_capped(tmp_path):
    for i in range(MAX_ENTRIES + 5):
        (tmp_path / f"f{i:03}.txt").write_text("")

    assert "… and 5 more" in build_project_context("x", tmp_path)


def test_long_instructions_are_truncated(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("a" * 30_000)

    context = build_project_context("x", tmp_path)

    assert "from CLAUDE.md" in context
    assert "[… truncated]" in context
    assert len(context) < 25_000


def test_a_detached_head_shows_the_commit(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("0123456789abcdef\n")

    assert git_branch(tmp_path) == "0123456"
    assert git_branch(tmp_path / "not-a-repo") is None
