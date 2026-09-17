import pytest
from conftest import FakeProvider, parse_sse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from netherbrain.api.deps import get_session_factory
from netherbrain.db.models import Message
from netherbrain.db.repository import make_title
from netherbrain.db.session import create_engine
from netherbrain.main import app
from netherbrain.schemas import ReasoningEvent, TokenEvent, UsageEvent

MISSING_ID = "01a09034-355e-71a4-8403-8a1b1710aa0f"


def new_conversation(client) -> str:
    return client.post("/api/conversations").json()["id"]


def send(client, conversation_id: str, content: str = "Salut", provider: str = "fake"):
    return client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"provider": provider, "model": "fake-model", "content": content},
    )


async def count_messages(session_factory) -> int:
    async with session_factory() as session:
        return await session.scalar(select(func.count()).select_from(Message))


def test_a_conversation_is_listed_once_it_has_a_message(client, use_providers):
    use_providers(FakeProvider(events=[TokenEvent(content="ok")]))
    response = client.post("/api/conversations")

    assert response.status_code == 201
    conversation = response.json()
    assert conversation["title"] is None
    # Vide, elle n'apparaît pas encore : joindre un fichier crée une conversation vide.
    assert client.get("/api/conversations").json() == []

    send(client, conversation["id"])

    assert [c["id"] for c in client.get("/api/conversations").json()] == [conversation["id"]]


def test_sending_a_message_streams_and_saves_both_sides(client, use_providers):
    use_providers(
        FakeProvider(
            events=[
                ReasoningEvent(content="Hmm"),
                TokenEvent(content="Bon"),
                TokenEvent(content="jour"),
                UsageEvent(prompt_tokens=3, completion_tokens=2),
            ]
        )
    )
    conversation_id = new_conversation(client)

    response = send(client, conversation_id, "Salut toi")

    assert [name for name, _ in parse_sse(response.text)] == ["reasoning", "token", "token", "done"]
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["title"] == "Salut toi"
    user, assistant = detail["messages"]
    assert (user["role"], user["content"]) == ("user", "Salut toi")
    assert assistant["role"] == "assistant"
    assert (assistant["content"], assistant["reasoning"]) == ("Bonjour", "Hmm")
    assert (assistant["provider"], assistant["model"]) == ("fake", "fake-model")
    assert assistant["metrics"]["completion_tokens"] == 2
    assert assistant["stopped"] is False


def test_the_model_receives_the_whole_conversation(client, use_providers):
    provider = FakeProvider(events=[TokenEvent(content="Réponse")])
    use_providers(provider)
    conversation_id = new_conversation(client)

    send(client, conversation_id, "Premier")
    send(client, conversation_id, "Second")

    assert [(m.role, m.content) for m in provider.received] == [
        ("user", "Premier"),
        ("assistant", "Réponse"),
        ("user", "Second"),
    ]


def test_a_provider_failure_is_saved_with_the_partial_answer(client, use_providers):
    use_providers(FakeProvider(events=[TokenEvent(content="Début")], fail=True))
    conversation_id = new_conversation(client)

    send(client, conversation_id)

    assistant = client.get(f"/api/conversations/{conversation_id}").json()["messages"][-1]
    assert assistant["content"] == "Début"
    assert assistant["error"] == "fake: connection lost"
    assert assistant["stopped"] is False


def test_the_most_recently_active_conversation_comes_first(client, use_providers):
    use_providers(FakeProvider(events=[TokenEvent(content="ok")]))
    older = new_conversation(client)
    newer = new_conversation(client)
    send(client, older, "Première")
    send(client, newer, "Deuxième")

    send(client, older, "Je relance la plus ancienne")

    assert [c["id"] for c in client.get("/api/conversations").json()] == [older, newer]


def test_deleting_a_conversation_deletes_its_messages(client, use_providers):
    use_providers(FakeProvider(events=[TokenEvent(content="ok")]))
    conversation_id = new_conversation(client)
    send(client, conversation_id)

    assert client.delete(f"/api/conversations/{conversation_id}").status_code == 204

    assert client.get(f"/api/conversations/{conversation_id}").status_code == 404
    assert client.portal.call(count_messages, client.session_factory) == 0


def test_an_unknown_conversation_returns_404(client, use_providers):
    use_providers(FakeProvider())

    assert client.get(f"/api/conversations/{MISSING_ID}").status_code == 404
    assert client.delete(f"/api/conversations/{MISSING_ID}").status_code == 404
    assert send(client, MISSING_ID).status_code == 404


def test_an_unknown_provider_returns_404_and_saves_nothing(client, use_providers):
    use_providers(FakeProvider())
    conversation_id = new_conversation(client)

    assert send(client, conversation_id, provider="nope").status_code == 404
    assert client.get(f"/api/conversations/{conversation_id}").json()["messages"] == []


def test_an_empty_message_is_rejected(client, use_providers):
    use_providers(FakeProvider())
    conversation_id = new_conversation(client)

    assert send(client, conversation_id, content="").status_code == 422


def test_a_database_outage_returns_503(client):
    # Rien n'écoute sur le port 1 : la connexion est refusée immédiatement.
    engine = create_engine("postgresql+asyncpg://user:secret@127.0.0.1:1/netherbrain")
    app.dependency_overrides[get_session_factory] = lambda: async_sessionmaker(engine)

    response = client.get("/api/conversations")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("Salut", "Salut"),
        ("  plusieurs   espaces\net des lignes  ", "plusieurs espaces et des lignes"),
        ("mot " * 30, ("mot " * 15).strip() + "…"),
    ],
)
def test_make_title(content, expected):
    assert make_title(content) == expected
