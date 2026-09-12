"""L'agent de code : ses outils, leurs autorisations, et la boucle qui les enchaîne."""

import asyncio
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from conftest import FakeProvider, parse_sse

from netherbrain.agent.approvals import ApprovalRegistry
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
    assert [schema["function"]["name"] for schema in provider.tools] == [
        "list_files",
        "read_file",
        "search_files",
        "write_file",
        "edit_file",
        "run_command",
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
        ("read_file", '{"path": "../secret.txt"}', "outside"),
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


def test_answering_an_unknown_approval_is_404(client, workspace, approvals):
    conversation_id = client.post("/api/conversations").json()["id"]

    assert decide(client, conversation_id, "nope", "once").status_code == 404


def test_models_say_which_ones_can_use_tools(client, use_providers):
    use_providers(FakeProvider(capabilities=["tools"]), FakeProvider(name="other"))

    models = client.get("/api/models").json()["models"]

    assert {(m["provider"], m["tools"]) for m in models} == {("fake", True), ("other", False)}


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
