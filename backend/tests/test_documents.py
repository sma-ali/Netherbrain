"""Import des documents et RAG dans le chat, de bout en bout (avec de faux modèles)."""

from conftest import FakeEmbedder, FakeProvider, parse_sse
from sqlalchemy import func, select

from netherbrain.config import Settings, get_settings
from netherbrain.db.models import DocumentChunk
from netherbrain.main import app
from netherbrain.schemas import TokenEvent

SECRET = "Le mot de passe du coffre est licorne. Il ne faut le dire à personne."
RECIPE = "Pour la tarte aux pommes, il faut des pommes, du beurre et de la farine."
QUESTION = "Quel est le mot de passe du coffre ?"


def upload(client, name: str, content: str | bytes):
    data = content.encode() if isinstance(content, str) else content
    return client.post("/api/documents", files={"file": (name, data, "text/plain")})


def ask(client, question: str = QUESTION, use_documents: bool = True):
    conversation_id = client.post("/api/conversations").json()["id"]
    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={
            "provider": "fake",
            "model": "fake-model",
            "content": question,
            "use_documents": use_documents,
        },
    )
    return conversation_id, response


async def count_chunks(session_factory) -> int:
    async with session_factory() as session:
        return await session.scalar(select(func.count()).select_from(DocumentChunk))


# --- Import et indexation ---


def test_an_uploaded_document_is_indexed_in_the_background(client, use_embedder):
    use_embedder(FakeEmbedder())

    response = upload(client, "secret.txt", SECRET)

    assert response.status_code == 202
    assert response.json()["status"] == "processing"
    # Avec TestClient, la tâche de fond est finie quand la requête rend la main.
    document = client.get("/api/documents").json()[0]
    assert (document["name"], document["status"], document["chunk_count"]) == (
        "secret.txt",
        "ready",
        1,
    )


def test_an_embedding_failure_puts_the_document_in_error(client, use_embedder):
    use_embedder(FakeEmbedder(fail=True))

    upload(client, "secret.txt", SECRET)

    document = client.get("/api/documents").json()[0]
    assert document["status"] == "error"
    assert "unreachable" in document["error"]


def test_a_document_without_text_is_in_error(client, use_embedder):
    use_embedder(FakeEmbedder())

    upload(client, "vide.txt", "   ")

    assert client.get("/api/documents").json()[0]["status"] == "error"


def test_unsupported_files_are_refused(client, use_embedder):
    use_embedder(FakeEmbedder())

    response = upload(client, "photo.png", b"\x89PNG")

    assert response.status_code == 415
    assert client.get("/api/documents").json() == []


def test_files_that_are_too_large_are_refused(client, use_embedder):
    use_embedder(FakeEmbedder())
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, max_upload_mb=1)

    response = upload(client, "gros.txt", "a" * (1024 * 1024 + 1))

    assert response.status_code == 413


def test_deleting_a_document_deletes_its_chunks(client, use_embedder):
    use_embedder(FakeEmbedder())
    document_id = upload(client, "secret.txt", SECRET).json()["id"]

    assert client.delete(f"/api/documents/{document_id}").status_code == 204

    assert client.get("/api/documents").json() == []
    assert client.portal.call(count_chunks, client.session_factory) == 0


# --- RAG dans le chat ---


def test_the_answer_is_grounded_in_the_most_relevant_document(client, use_providers, use_embedder):
    use_embedder(FakeEmbedder())
    provider = FakeProvider(events=[TokenEvent(content="C'est « licorne » [1].")])
    use_providers(provider)
    upload(client, "secret.txt", SECRET)
    upload(client, "recette.txt", RECIPE)

    conversation_id, response = ask(client)

    name, payload = parse_sse(response.text)[0]
    assert name == "sources"
    assert payload["sources"][0]["document_name"] == "secret.txt"
    assert payload["warning"] is None
    # Le modèle reçoit les extraits numérotés en message système, puis la question.
    system, *_, question = provider.received
    assert system.role == "system"
    assert "[1] (secret.txt)" in system.content and "licorne" in system.content
    assert question.content == QUESTION
    saved = client.get(f"/api/conversations/{conversation_id}").json()["messages"][-1]
    assert saved["sources"][0]["document_name"] == "secret.txt"


def test_documents_are_only_used_when_asked(client, use_providers, use_embedder):
    use_embedder(FakeEmbedder())
    provider = FakeProvider(events=[TokenEvent(content="Je ne sais pas.")])
    use_providers(provider)
    upload(client, "secret.txt", SECRET)

    conversation_id, response = ask(client, use_documents=False)

    assert [name for name, _ in parse_sse(response.text)] == ["token", "done"]
    assert [m.role for m in provider.received] == ["user"]
    saved = client.get(f"/api/conversations/{conversation_id}").json()["messages"][-1]
    assert saved["sources"] is None


def test_without_the_embedding_model_the_answer_comes_without_documents(
    client, use_providers, use_embedder
):
    use_embedder(FakeEmbedder())
    provider = FakeProvider(events=[TokenEvent(content="Réponse")])
    use_providers(provider)
    upload(client, "secret.txt", SECRET)
    use_embedder(FakeEmbedder(fail=True))

    _, response = ask(client)

    events = parse_sse(response.text)
    assert events[0][0] == "sources"
    assert events[0][1]["sources"] == []
    assert "unreachable" in events[0][1]["warning"]
    assert events[-1][0] == "done"
    assert [m.role for m in provider.received] == ["user"]
