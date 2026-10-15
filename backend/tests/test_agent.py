"""L'agent de code : ses outils, leurs autorisations, et la boucle qui les enchaîne."""

import asyncio
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from conftest import FakeProvider, parse_sse

from netherbrain.agent import diff as diff_module
from netherbrain.agent.approvals import ApprovalRegistry
from netherbrain.agent.diff import make_diff
from netherbrain.agent.tools import Toolbox
from netherbrain.config import Settings, get_settings
from netherbrain.main import app
from netherbrain.schemas import TokenEvent, ToolCallEvent


def tool_call(name: str, arguments: str = "{}", call_id: str = "call_1") -> ToolCallEvent:
    return ToolCallEvent(id=call_id, name=name, arguments=arguments)


def make_project(client, workspace, files: dict[str, str], name: str = "nb") -> tuple[str, Path]:
    """Un projet avec quelques fichiers, et une conversation dedans."""
    folder = workspace / name
    folder.mkdir(parents=True, exist_ok=True)
    for path, content in files.items():
        (folder / path).parent.mkdir(parents=True, exist_ok=True)
        (folder / path).write_text(content)
    project_id = client.post("/api/projects", json={"path": name}).json()["id"]
    conversation_id = client.post("/api/conversations", json={"project_id": project_id}).json()[
        "id"
    ]
    return conversation_id, folder


def ask(client, conversation_id: str, content: str = "Vas-y", **fields):
    return client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={
            "provider": "fake",
            "model": "fake-model",
            "content": content,
            "agent": True,
            **fields,
        },
    )


def decide(client, conversation_id: str, call_id: str, decision: str):
    return client.post(
        f"/api/conversations/{conversation_id}/approvals/{call_id}", json={"decision": decision}
    )


def names(response) -> list[str]:
    return [name for name, _ in parse_sse(response.text)]


def event_of(response, name: str) -> dict:
    return next(data for event, data in parse_sse(response.text) if event == name)


def wait_for_request(approvals: ApprovalRegistry, conversation_id: str, timeout: float = 5) -> str:
    """Attend que le stream demande une autorisation, et renvoie l'appel concerné."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pending = approvals.pending_calls(uuid.UUID(conversation_id))
        if pending:
            return pending[0]
        time.sleep(0.02)
    raise AssertionError("aucune demande d'autorisation n'est arrivée")


# --- La boucle de l'agent ---


def test_the_model_reads_a_file_then_answers(client, workspace, use_providers, approvals):
    provider = FakeProvider(
        turns=[
            [tool_call("read_file", '{"path": "app.py"}')],
            [TokenEvent(content="Il affiche bonjour.")],
        ]
    )
    use_providers(provider)
    conversation_id, _ = make_project(client, workspace, {"app.py": "print('bonjour')\n"})

    response = ask(client, conversation_id, "Que fait app.py ?")

    assert names(response) == ["tool_call", "tool_result", "token", "done"]
    step = event_of(response, "tool_result")
    assert (step["summary"], step["status"]) == ("read_file(app.py)", "done")
    assert "print('bonjour')" in step["output"]
    # Le modèle reçoit la liste des outils, puis le résultat comme message « tool ».
    # Hors d'un dépôt Git, pas d'outils Git.
    assert [schema["function"]["name"] for schema in provider.tools] == [
        "list_files",
        "read_file",
        "search_files",
        "write_file",
        "edit_file",
        "run_command",
        "ask_user",
    ]
    assert provider.histories[1][-1].role == "tool"
    assert provider.histories[1][-2].tool_calls[0]["function"]["name"] == "read_file"


def test_the_tools_used_are_saved_with_the_answer(client, workspace, use_providers, approvals):
    use_providers(
        FakeProvider(turns=[[tool_call("list_files")], [TokenEvent(content="Un seul fichier.")]])
    )
    conversation_id, _ = make_project(client, workspace, {"app.py": "x = 1\n"})

    ask(client, conversation_id)

    answer = client.get(f"/api/conversations/{conversation_id}").json()["messages"][-1]
    assert [step["name"] for step in answer["steps"]] == ["list_files"]
    assert answer["metrics"]["tool_calls"] == 1


def test_agent_mode_needs_a_project(client, workspace, use_providers, approvals):
    use_providers(FakeProvider())
    conversation_id = client.post("/api/conversations").json()["id"]

    assert ask(client, conversation_id).status_code == 400


def test_the_agent_receives_its_instructions(client, workspace, use_providers, approvals):
    provider = FakeProvider(events=[TokenEvent(content="ok")])
    use_providers(provider)
    conversation_id, _ = make_project(client, workspace, {"app.py": "x = 1\n"})

    ask(client, conversation_id)

    system = provider.received[0]
    assert system.role == "system"
    assert "Read before you write" in system.content


def test_the_loop_stops_after_too_many_steps(client, workspace, use_providers, approvals):
    app.dependency_overrides[get_settings] = lambda: Settings(agent_max_steps=2)
    # Ce modèle redemande un outil à chaque tour, sans jamais conclure.
    use_providers(FakeProvider(events=[tool_call("list_files")]))
    conversation_id, _ = make_project(client, workspace, {"app.py": "x = 1\n"})

    response = ask(client, conversation_id)

    assert names(response).count("tool_call") == 2
    assert event_of(response, "error")["message"] == "Stopped after 2 tool calls."


@pytest.mark.parametrize(
    ("name", "arguments", "expected"),
    [
        ("read_file", "{oops", "not valid JSON"),
        ("delete_everything", "{}", "Unknown tool"),
        ("read_file", '{"nope": 1}', "Bad arguments"),
        ("read_file", '{"path": "/etc/hostname"}', "outside"),
        ("read_file", '{"path": "../../secret.txt"}', "outside"),
    ],
)
def test_a_bad_call_is_reported_to_the_model(
    client, workspace, use_providers, approvals, name, arguments, expected
):
    (workspace / "secret.txt").write_text("mot de passe")
    provider = FakeProvider(
        turns=[[tool_call(name, arguments)], [TokenEvent(content="Je n'y arrive pas.")]]
    )
    use_providers(provider)
    conversation_id, _ = make_project(client, workspace, {"app.py": "x = 1\n"})

    response = ask(client, conversation_id)

    step = event_of(response, "tool_result")
    assert step["status"] == "error"
    assert expected in step["output"]


# --- Autorisations ---


def test_writing_a_file_waits_for_the_user(client, workspace, use_providers, approvals):
    use_providers(
        FakeProvider(
            turns=[
                [tool_call("write_file", '{"path": "notes.md", "content": "salut"}')],
                [TokenEvent(content="C'est écrit.")],
            ]
        )
    )
    conversation_id, folder = make_project(client, workspace, {"app.py": "x = 1\n"})

    # La requête reste ouverte tant que l'utilisateur n'a pas répondu : on la lance à part.
    with ThreadPoolExecutor(1) as pool:
        streaming = pool.submit(ask, client, conversation_id)
        call_id = wait_for_request(approvals, conversation_id)
        assert not (folder / "notes.md").exists()  # rien n'est écrit avant l'accord
        assert decide(client, conversation_id, call_id, "once").status_code == 204
        response = streaming.result(timeout=10)

    assert names(response) == ["tool_call", "tool_request", "tool_result", "token", "done"]
    assert (folder / "notes.md").read_text() == "salut"
    # La demande montrait le fichier à créer, avant qu'il existe.
    [diff] = event_of(response, "tool_request")["diffs"]
    assert (diff["created"], diff["lines"]) == (True, ["@@ -0,0 +1 @@", "+salut"])


def test_an_edit_shows_its_diff_and_keeps_it_in_the_history(
    client, workspace, use_providers, approvals
):
    edit = '{"path": "app.py", "old_string": "print(1)", "new_string": "print(2)"}'
    use_providers(
        FakeProvider(turns=[[tool_call("edit_file", edit)], [TokenEvent(content="Modifié.")]])
    )
    conversation_id, folder = make_project(client, workspace, {"app.py": "x = 1\nprint(1)\n"})

    with ThreadPoolExecutor(1) as pool:
        streaming = pool.submit(ask, client, conversation_id)
        decide(client, conversation_id, wait_for_request(approvals, conversation_id), "once")
        response = streaming.result(timeout=10)

    expected = ["@@ -1,2 +1,2 @@", " x = 1", "-print(1)", "+print(2)"]
    assert event_of(response, "tool_request")["diffs"][0]["lines"] == expected
    [step] = client.get(f"/api/conversations/{conversation_id}").json()["messages"][-1]["steps"]
    [diff] = step["diffs"]
    assert (step["status"], diff["added"], diff["removed"]) == ("done", 1, 1)
    assert diff["lines"] == expected
    assert (folder / "app.py").read_text() == "x = 1\nprint(2)\n"


def test_a_refusal_is_told_to_the_model(client, workspace, use_providers, approvals):
    provider = FakeProvider(
        turns=[
            [tool_call("run_command", '{"command": "echo bonjour"}')],
            [TokenEvent(content="D'accord, je ne lance rien.")],
        ]
    )
    use_providers(provider)
    conversation_id, _ = make_project(client, workspace, {"app.py": "x = 1\n"})

    with ThreadPoolExecutor(1) as pool:
        streaming = pool.submit(ask, client, conversation_id)
        call_id = wait_for_request(approvals, conversation_id)
        decide(client, conversation_id, call_id, "deny")
        response = streaming.result(timeout=10)

    step = event_of(response, "tool_result")
    assert step["status"] == "denied"
    assert provider.histories[1][-1].content == "The user refused this action."


def test_allowing_a_tool_once_and_for_all(client, workspace, use_providers, approvals):
    use_providers(
        FakeProvider(
            turns=[
                [tool_call("write_file", '{"path": "a.txt", "content": "1"}', call_id="c1")],
                [tool_call("write_file", '{"path": "b.txt", "content": "2"}', call_id="c2")],
                [TokenEvent(content="Les deux sont écrits.")],
            ]
        )
    )
    conversation_id, folder = make_project(client, workspace, {"app.py": "x = 1\n"})

    with ThreadPoolExecutor(1) as pool:
        streaming = pool.submit(ask, client, conversation_id)
        decide(client, conversation_id, wait_for_request(approvals, conversation_id), "always")
        response = streaming.result(timeout=10)

    # Le second appel ne repose plus la question.
    assert names(response).count("tool_request") == 1
    assert (folder / "a.txt").read_text() == "1"
    assert (folder / "b.txt").read_text() == "2"


def test_without_commands_the_model_is_not_offered_them(
    client, workspace, use_providers, approvals
):
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, agent_allow_commands=False
    )
    provider = FakeProvider(
        turns=[
            [tool_call("run_command", '{"command": "echo bonjour"}')],
            [TokenEvent(content="Je ne peux pas lancer de commande.")],
        ]
    )
    use_providers(provider)
    conversation_id, _ = make_project(client, workspace, {"app.py": "x = 1\n"})

    response = ask(client, conversation_id)

    # Refusé d'office : aucune demande d'autorisation, et le modèle sait pourquoi.
    assert names(response) == ["tool_call", "tool_result", "token", "done"]
    assert "run_command" not in [schema["function"]["name"] for schema in provider.tools]
    assert provider.histories[1][-1].content == "Commands are turned off on this server."


def test_answering_an_unknown_approval_is_404(client, workspace, approvals):
    conversation_id = client.post("/api/conversations").json()["id"]

    assert decide(client, conversation_id, "nope", "once").status_code == 404


def test_models_say_which_ones_can_use_tools(client, use_providers):
    use_providers(FakeProvider(capabilities=["tools"]), FakeProvider(name="other"))

    models = client.get("/api/models").json()["models"]

    assert {(m["provider"], m["tools"]) for m in models} == {("fake", True), ("other", False)}


def test_the_agent_can_ask_the_user_a_question(client, workspace, use_providers, approvals):
    provider = FakeProvider(
        turns=[
            [
                tool_call(
                    "ask_user", '{"question": "Quel framework ?", "options": ["FastAPI", "Flask"]}'
                )
            ],
            [TokenEvent(content="Va pour FastAPI.")],
        ]
    )
    use_providers(provider)
    conversation_id, _ = make_project(client, workspace, {"app.py": "x = 1\n"})

    with ThreadPoolExecutor(1) as pool:
        streaming = pool.submit(ask, client, conversation_id)
        call_id = wait_for_request(approvals, conversation_id)
        reply = client.post(
            f"/api/conversations/{conversation_id}/approvals/{call_id}",
            json={"decision": "answer", "answer": "FastAPI"},
        )
        assert reply.status_code == 204
        response = streaming.result(timeout=10)

    request = event_of(response, "tool_request")
    assert (request["kind"], request["question"], request["options"]) == (
        "question",
        "Quel framework ?",
        ["FastAPI", "Flask"],
    )
    assert event_of(response, "tool_result")["status"] == "done"
    assert provider.histories[1][-1].content == "The user answered: FastAPI"


def test_an_answer_needs_some_text(client, workspace, approvals):
    conversation_id = client.post("/api/conversations").json()["id"]

    assert decide(client, conversation_id, "call_1", "answer").status_code == 422


# --- Les outils, un par un ---


def run(toolbox: Toolbox, name: str, **arguments) -> str:
    return asyncio.run(toolbox.run(name, arguments)).output


def test_list_files_ignores_the_noise(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x = 1")
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "index.js").write_text("")
    (tmp_path / ".env").write_text("SECRET=1")

    assert run(Toolbox(tmp_path), "list_files") == "src/\nsrc/app.py"


def test_read_file_numbers_the_lines_and_says_what_remains(tmp_path):
    (tmp_path / "long.txt").write_text("".join(f"ligne {i}\n" for i in range(10)))

    output = run(Toolbox(tmp_path), "read_file", path="long.txt", offset=2, limit=3)

    assert output.splitlines()[0] == "    2  ligne 1"
    assert "6 more lines" in output


def test_search_files_finds_the_line(tmp_path):
    (tmp_path / "app.py").write_text("import os\nSECRET = 42\n")

    assert run(Toolbox(tmp_path), "search_files", pattern=r"SECRET\s*=") == "app.py:2: SECRET = 42"


def test_edit_file_needs_a_unique_excerpt(tmp_path):
    (tmp_path / "app.py").write_text("a = 1\na = 1\n")
    toolbox = Toolbox(tmp_path)

    assert "appears 2 times" in run(
        toolbox, "edit_file", path="app.py", old_string="a = 1", new_string="b = 2"
    )
    assert "was not found" in run(
        toolbox, "edit_file", path="app.py", old_string="zzz", new_string=""
    )

    assert run(toolbox, "edit_file", path="app.py", old_string="a = 1\na", new_string="c = 3\na")
    assert (tmp_path / "app.py").read_text() == "c = 3\na = 1\n"


def preview(toolbox: Toolbox, name: str, **arguments):
    return asyncio.run(toolbox.preview(name, arguments))


def test_a_diff_shows_the_changed_lines_with_some_context():
    old = "".join(f"ligne {i}\n" for i in range(1, 11))

    diff = make_diff("notes.txt", old, old.replace("ligne 5\n", "ligne cinq\nligne 5 bis\n"))

    # Le bloc commence ligne 2 et couvre 7 lignes avant, 8 après : 3 lignes de contexte
    # de chaque côté du changement.
    assert diff.lines == [
        "@@ -2,7 +2,8 @@",
        " ligne 2",
        " ligne 3",
        " ligne 4",
        "-ligne 5",
        "+ligne cinq",
        "+ligne 5 bis",
        " ligne 6",
        " ligne 7",
        " ligne 8",
    ]
    assert (diff.added, diff.removed, diff.truncated) == (2, 1, False)


def test_a_long_diff_is_cut_but_still_counted(monkeypatch):
    monkeypatch.setattr(diff_module, "MAX_DIFF_LINES", 10)

    diff = make_diff("gros.txt", "", "".join(f"{i}\n" for i in range(100)), created=True)

    assert (len(diff.lines), diff.added, diff.truncated) == (10, 100, True)


def test_a_preview_changes_nothing_on_disk(tmp_path):
    (tmp_path / "app.py").write_text("a = 1\na = 1\n")
    toolbox = Toolbox(tmp_path)

    [created] = preview(toolbox, "write_file", path="src/new.py", content="b = 2\n")
    assert (created.created, created.lines) == (True, ["@@ -0,0 +1 @@", "+b = 2"])
    assert not (tmp_path / "src").exists()

    [replaced] = preview(toolbox, "write_file", path="app.py", content="a = 1\n")
    assert (replaced.created, replaced.removed) == (False, 1)
    assert (tmp_path / "app.py").read_text() == "a = 1\na = 1\n"


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("read_file", {"path": "app.py"}),
        # Un extrait qui apparaît deux fois : l'outil refusera, il n'y a rien à montrer.
        ("edit_file", {"path": "app.py", "old_string": "a = 1", "new_string": "b = 2"}),
        ("edit_file", {"path": "absent.py", "old_string": "a", "new_string": "b"}),
        ("write_file", {"path": "../ailleurs.py", "content": "x"}),
        ("write_file", {"path": "app.py", "content": 42}),
    ],
)
def test_no_preview_for_other_tools_or_doomed_calls(tmp_path, name, arguments):
    (tmp_path / "app.py").write_text("a = 1\na = 1\n")

    assert preview(Toolbox(tmp_path), name, **arguments) == []


def test_commands_do_not_see_the_server_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("NETHERBRAIN_OPENROUTER_API_KEY", "sk-or-secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-secret")

    output = run(Toolbox(tmp_path), "run_command", command="env")

    assert "sk-or-secret" not in output
    assert "aws-secret" not in output
    # Ce qu'il faut pour trouver les programmes est toujours là.
    assert "PATH=" in output


def test_commands_can_be_turned_off(tmp_path):
    toolbox = Toolbox(tmp_path, allow_commands=False)

    assert "run_command" not in [schema["function"]["name"] for schema in toolbox.schemas]
    assert not toolbox.needs_approval("run_command")
    assert toolbox.needs_approval("write_file")
    assert run(toolbox, "run_command", command="touch trace") == (
        "Commands are turned off on this server."
    )
    assert not (tmp_path / "trace").exists()


def test_run_command_reports_the_exit_code(tmp_path):
    toolbox = Toolbox(tmp_path)

    assert run(toolbox, "run_command", command="echo bonjour") == "exit code 0\nbonjour"
    assert run(toolbox, "run_command", command="exit 3").startswith("exit code 3")


def test_a_command_that_never_ends_is_stopped(tmp_path):
    assert "stopped after 1s" in run(
        Toolbox(tmp_path, command_timeout=1), "run_command", command="sleep 5"
    )


def test_the_output_is_truncated(tmp_path):
    (tmp_path / "big.txt").write_text("a" * 5000)

    output = run(Toolbox(tmp_path, max_output_chars=100), "read_file", path="big.txt")

    assert len(output) < 200
    assert "truncated" in output


# --- Git ---


def git_repository(folder: Path, files: dict[str, str]) -> Toolbox:
    """Un dépôt avec un premier commit, fait par l'agent lui-même."""
    subprocess.run(["git", "init", "--quiet", "-b", "main"], cwd=folder, check=True)
    for path, content in files.items():
        (folder / path).write_text(content)
    toolbox = Toolbox(folder)
    assert run(toolbox, "git_commit", message="Premier commit").startswith("Committed")
    return toolbox


def names_of(toolbox: Toolbox) -> list[str]:
    return [schema["function"]["name"] for schema in toolbox.schemas]


def test_git_tools_are_only_offered_in_a_repository(tmp_path):
    assert "git_status" not in names_of(Toolbox(tmp_path))

    toolbox = git_repository(tmp_path, {"app.py": "print(1)\n"})

    assert {"git_status", "git_diff", "git_log", "git_commit"} <= set(names_of(toolbox))
    assert toolbox.needs_approval("git_commit")
    assert not toolbox.needs_approval("git_diff")


def test_the_agent_sees_what_changed_then_commits_it(tmp_path):
    toolbox = git_repository(tmp_path, {"app.py": "print(1)\n"})
    (tmp_path / "app.py").write_text("print(2)\n")
    (tmp_path / "notes.md").write_text("# Notes\n")

    status = run(toolbox, "git_status")
    assert " M app.py" in status and "?? notes.md" in status
    assert "-print(1)\n+print(2)" in run(toolbox, "git_diff", path="app.py")

    # L'aperçu du commit : tous les fichiers, nouveaux compris, sans rien enregistrer.
    changes = preview(toolbox, "git_commit", message="Afficher 2")
    assert [(diff.path, diff.created, diff.added, diff.removed) for diff in changes] == [
        ("app.py", False, 1, 1),
        ("notes.md", True, 1, 0),
    ]
    assert "?? notes.md" in run(toolbox, "git_status")

    output = run(toolbox, "git_commit", message="Afficher 2")

    assert output.startswith("Committed") and "2 files changed" in output
    assert run(toolbox, "git_status") == "## main"
    log = subprocess.run(
        ["git", "log", "-1", "--format=%an|%s"], cwd=tmp_path, capture_output=True, text=True
    )
    assert log.stdout.strip() == "Netherbrain agent|Afficher 2"
    assert "Nothing to commit" in run(toolbox, "git_commit", message="Rien")


def test_a_commit_never_runs_the_repository_hooks(tmp_path):
    toolbox = git_repository(tmp_path, {"app.py": "x = 1\n"})
    # Un dépôt piégé : son hook s'exécuterait au commit, avec les droits de l'API.
    hook = tmp_path / ".git" / "hooks" / "pre-commit"
    hook.write_text(f"#!/bin/sh\ntouch {tmp_path / 'pwned'}\n")
    hook.chmod(0o755)
    (tmp_path / "app.py").write_text("x = 2\n")

    assert run(toolbox, "git_commit", message="Changer x").startswith("Committed")
    assert not (tmp_path / "pwned").exists()


def test_git_diff_stays_inside_the_project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    toolbox = git_repository(project, {"app.py": "x = 1\n"})

    assert "outside" in run(toolbox, "git_diff", path="..")
    assert "No commits yet." == run(Toolbox(_empty_repository(tmp_path / "vide")), "git_log")


def _empty_repository(folder: Path) -> Path:
    folder.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=folder, check=True)
    return folder


def test_a_commit_waits_for_the_user_who_sees_the_changes(
    client, workspace, use_providers, approvals
):
    use_providers(
        FakeProvider(
            turns=[
                [tool_call("git_commit", '{"message": "Ajouter les notes"}')],
                [TokenEvent(content="C'est enregistré.")],
            ]
        )
    )
    conversation_id, folder = make_project(client, workspace, {"app.py": "x = 1\n"})
    git_repository(folder, {})
    (folder / "notes.md").write_text("# Notes\n")

    with ThreadPoolExecutor(1) as pool:
        streaming = pool.submit(ask, client, conversation_id)
        call_id = wait_for_request(approvals, conversation_id)
        # Rien n'est commité avant l'accord.
        assert "notes.md" in run(Toolbox(folder), "git_status")
        decide(client, conversation_id, call_id, "once")
        response = streaming.result(timeout=10)

    request = event_of(response, "tool_request")
    assert request["summary"] == "git_commit(Ajouter les notes)"
    assert [diff["path"] for diff in request["diffs"]] == ["notes.md"]
    assert event_of(response, "tool_result")["status"] == "done"
    assert run(Toolbox(folder), "git_status") == "## main"
