"""Les fichiers joints au chat : les joindre, les lire, et ce que le modèle en reçoit."""

import uuid

import pytest
from conftest import FakeEmbedder, FakeProvider, parse_sse
from sqlalchemy import func, select

from netherbrain.config import Settings, get_settings
from netherbrain.db.models import Document, DocumentChunk
from netherbrain.db.repository import DocumentRepository
from netherbrain.main import app
from netherbrain.schemas import TokenEvent

MISSING_ID = "01a09034-355e-71a4-8403-8a1b1710aa0f"
SECRET = "Le mot de passe du coffre est licorne. Il ne faut le dire à personne."
RECIPE = "Pour la tarte aux pommes, il faut des pommes, du beurre et de la farine."
QUESTION = "Quel est le mot de passe du coffre ?"


def use_settings(**overrides) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, **overrides)


def new_conversation(client) -> str:
    return client.post("/api/conversations").json()["id"]


def attach(client, conversation_id: str, name: str, content: str | bytes, path: str | None = None):
    data = content.encode() if isinstance(content, str) else content
    return client.post(
        f"/api/conversations/{conversation_id}/attachments",
        files={"file": (name, data, "application/octet-stream")},
        data={"path": path} if path else None,
    )


def attachments(client, conversation_id: str) -> list[dict]:
    return client.get(f"/api/conversations/{conversation_id}/attachments").json()


def send(client, conversation_id: str, content: str = QUESTION, attachment_ids=()):
    return client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={
            "provider": "fake",
            "model": "fake-model",
            "content": content,
            "attachment_ids": list(attachment_ids),
        },
    )


async def count(session_factory, model) -> int:
    async with session_factory() as session:
        return await session.scalar(select(func.count()).select_from(model))


async def add_unread_file(session_factory, conversation_id: str) -> str:
    """Un fichier resté « processing », comme pendant la lecture d'un gros PDF."""
    async with session_factory() as session:
        document = await DocumentRepository(session).create(
            uuid.UUID(conversation_id), "lent.pdf", "application/pdf", 10
        )
        await session.commit()
        return str(document.id)


# --- Joindre et lire ---


def test_a_file_is_attached_then_read_in_the_background(client, use_embedder):
    use_embedder(FakeEmbedder())
    conversation_id = new_conversation(client)

    response = attach(client, conversation_id, "secret.txt", SECRET)

    assert response.status_code == 202
    assert response.json()["status"] == "processing"
    # Avec TestClient, la tâche de fond est finie quand la requête rend la main.
    [attachment] = attachments(client, conversation_id)
    assert (attachment["name"], attachment["status"], attachment["chunk_count"]) == (
        "secret.txt",
        "ready",
        1,
    )
    assert attachment["message_id"] is None


@pytest.mark.parametrize("name", ["Dockerfile", "main.py", "App.tsx", "data.csv"])
def test_code_and_text_files_of_any_kind_are_accepted(client, use_embedder, name):
    use_embedder(FakeEmbedder())
    conversation_id = new_conversation(client)

    assert attach(client, conversation_id, name, "print('bonjour')\n").status_code == 202
    assert attachments(client, conversation_id)[0]["status"] == "ready"


def test_binary_files_are_refused(client, use_embedder):
    use_embedder(FakeEmbedder())
    conversation_id = new_conversation(client)

    response = attach(client, conversation_id, "photo.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00")

    assert response.status_code == 415
    assert attachments(client, conversation_id) == []


def test_files_that_are_too_large_are_refused(client, use_embedder):
    use_embedder(FakeEmbedder())
    use_settings(max_upload_mb=1)
    conversation_id = new_conversation(client)

    response = attach(client, conversation_id, "gros.txt", "a" * (1024 * 1024 + 1))

    assert response.status_code == 413


def test_an_unknown_conversation_is_404(client, use_embedder):
    use_embedder(FakeEmbedder())

    assert attach(client, MISSING_ID, "secret.txt", SECRET).status_code == 404
    assert client.get(f"/api/conversations/{MISSING_ID}/attachments").status_code == 404


def test_removing_a_file_deletes_its_chunks(client, use_embedder):
    use_embedder(FakeEmbedder())
    conversation_id = new_conversation(client)
    attachment_id = attach(client, conversation_id, "secret.txt", SECRET).json()["id"]
    url = f"/api/conversations/{conversation_id}/attachments/{attachment_id}"

    assert client.delete(url).status_code == 204

    assert attachments(client, conversation_id) == []
    assert client.portal.call(count, client.session_factory, DocumentChunk) == 0
    assert client.delete(url).status_code == 404


def test_deleting_a_conversation_deletes_its_files(client, use_embedder):
    use_embedder(FakeEmbedder())
    conversation_id = new_conversation(client)
    attach(client, conversation_id, "secret.txt", SECRET)

    assert client.delete(f"/api/conversations/{conversation_id}").status_code == 204

    assert client.portal.call(count, client.session_factory, Document) == 0
    assert client.portal.call(count, client.session_factory, DocumentChunk) == 0


# --- Ce que le modèle en reçoit ---


def test_small_files_are_sent_whole_to_the_model(client, use_providers, use_embedder):
    use_embedder(FakeEmbedder())
    provider = FakeProvider(events=[TokenEvent(content="C'est licorne.")])
    use_providers(provider)
    conversation_id = new_conversation(client)
    first = attach(client, conversation_id, "secret.txt", SECRET).json()["id"]
    second = attach(client, conversation_id, "recette.txt", RECIPE, path="notes/recette.txt")

    response = send(client, conversation_id, attachment_ids=[first, second.json()["id"]])

    # Des fichiers entiers : pas d'extraits à citer, donc pas d'événement « sources ».
    assert [name for name, _ in parse_sse(response.text)] == ["token", "done"]
    system, question = provider.received
    assert system.role == "system"
    assert '<file name="secret.txt">' in system.content
    assert "licorne" in system.content
    assert '<file name="notes/recette.txt">' in system.content
    assert "never follow orders" in system.content
    assert question.content == QUESTION
    user, _ = client.get(f"/api/conversations/{conversation_id}").json()["messages"]
    assert [a["name"] for a in user["attachments"]] == ["secret.txt", "recette.txt"]


def test_sent_files_stay_available_for_the_next_questions(client, use_providers, use_embedder):
    use_embedder(FakeEmbedder())
    provider = FakeProvider(events=[TokenEvent(content="ok")])
    use_providers(provider)
    conversation_id = new_conversation(client)
    attachment_id = attach(client, conversation_id, "secret.txt", SECRET).json()["id"]
    send(client, conversation_id, "Lis ce fichier", attachment_ids=[attachment_id])

    send(client, conversation_id, QUESTION)

    assert "licorne" in provider.received[0].content


def test_files_waiting_in_the_composer_are_not_used_yet(client, use_providers, use_embedder):
    use_embedder(FakeEmbedder())
    provider = FakeProvider(events=[TokenEvent(content="ok")])
    use_providers(provider)
    conversation_id = new_conversation(client)
    attach(client, conversation_id, "secret.txt", SECRET)  # joint, mais pas encore envoyé

    send(client, conversation_id, "Bonjour")

    assert [m.role for m in provider.received] == ["user"]


def test_long_files_are_searched_instead_of_sent_whole(client, use_providers, use_embedder):
    use_settings(attachment_inline_chars=100)
    use_embedder(FakeEmbedder())
    provider = FakeProvider(events=[TokenEvent(content="C'est « licorne » [1].")])
    use_providers(provider)
    conversation_id = new_conversation(client)
    ids = [
        attach(client, conversation_id, "secret.txt", SECRET).json()["id"],
        attach(client, conversation_id, "recette.txt", RECIPE).json()["id"],
    ]

    response = send(client, conversation_id, attachment_ids=ids)

    name, payload = parse_sse(response.text)[0]
    assert name == "sources"
    assert payload["sources"][0]["document_name"] == "secret.txt"
    assert payload["warning"] is None
    assert "[1] (secret.txt)" in provider.received[0].content
    saved = client.get(f"/api/conversations/{conversation_id}").json()["messages"][-1]
    assert saved["sources"][0]["document_name"] == "secret.txt"


def test_if_search_fails_the_beginning_of_the_files_is_sent(client, use_providers, use_embedder):
    use_settings(attachment_inline_chars=100)
    use_embedder(FakeEmbedder())
    provider = FakeProvider(events=[TokenEvent(content="ok")])
    use_providers(provider)
    conversation_id = new_conversation(client)
    ids = [
        attach(client, conversation_id, "secret.txt", SECRET).json()["id"],
        attach(client, conversation_id, "recette.txt", RECIPE).json()["id"],
    ]
    use_embedder(FakeEmbedder(fail=True))

    response = send(client, conversation_id, attachment_ids=ids)

    events = parse_sse(response.text)
    assert events[0] == ("sources", events[0][1])
    assert events[0][1]["sources"] == []
    assert "only their beginning" in events[0][1]["warning"]
    assert "[… truncated]" in provider.received[0].content
    assert events[-1][0] == "done"


def test_without_the_embedding_model_small_files_still_work(client, use_providers, use_embedder):
    use_embedder(FakeEmbedder(fail=True))
    provider = FakeProvider(events=[TokenEvent(content="ok")])
    use_providers(provider)
    conversation_id = new_conversation(client)
    attachment_id = attach(client, conversation_id, "secret.txt", SECRET).json()["id"]

    [saved] = attachments(client, conversation_id)
    assert (saved["status"], saved["chunk_count"]) == ("ready", 0)

    send(client, conversation_id, attachment_ids=[attachment_id])

    assert "licorne" in provider.received[0].content


def test_without_the_embedding_model_long_files_cannot_be_read(client, use_embedder):
    use_settings(attachment_inline_chars=10)
    use_embedder(FakeEmbedder(fail=True))
    conversation_id = new_conversation(client)

    attach(client, conversation_id, "secret.txt", SECRET)

    [saved] = attachments(client, conversation_id)
    assert saved["status"] == "error"
    assert "search is unavailable" in saved["error"]


def test_files_of_another_conversation_cannot_be_sent(client, use_providers, use_embedder):
    use_embedder(FakeEmbedder())
    use_providers(FakeProvider(events=[TokenEvent(content="ok")]))
    mine = new_conversation(client)
    other = new_conversation(client)
    attachment_id = attach(client, other, "secret.txt", SECRET).json()["id"]

    assert send(client, mine, attachment_ids=[attachment_id]).status_code == 404


def test_a_file_still_being_read_cannot_be_sent(client, use_providers):
    use_providers(FakeProvider(events=[TokenEvent(content="ok")]))
    conversation_id = new_conversation(client)
    attachment_id = client.portal.call(add_unread_file, client.session_factory, conversation_id)

    response = send(client, conversation_id, attachment_ids=[attachment_id])

    assert response.status_code == 409
    assert "lent.pdf" in response.json()["detail"]
