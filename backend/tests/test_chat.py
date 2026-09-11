from conftest import FakeProvider, parse_sse

from netherbrain.schemas import ReasoningEvent, TokenEvent, UsageEvent

CHAT_BODY = {"model": "fake-model", "messages": [{"role": "user", "content": "Salut"}]}


def test_list_models(client, use_provider):
    use_provider(FakeProvider())

    response = client.get("/api/models")

    assert response.status_code == 200
    assert response.json() == [{"id": "fake-model", "provider": "fake"}]


def test_list_models_when_provider_is_down(client, use_provider):
    use_provider(FakeProvider(fail=True))

    response = client.get("/api/models")

    assert response.status_code == 503


def test_chat_streams_reasoning_tokens_then_metrics(client, use_provider):
    provider = use_provider(
        FakeProvider(
            [
                ReasoningEvent(content="Hmm..."),
                TokenEvent(content="Bon"),
                TokenEvent(content="jour"),
                UsageEvent(prompt_tokens=5, completion_tokens=2),
            ]
        )
    )

    response = client.post("/api/chat", json=CHAT_BODY)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    assert events[:3] == [
        ("reasoning", {"content": "Hmm..."}),
        ("token", {"content": "Bon"}),
        ("token", {"content": "jour"}),
    ]
    name, metrics = events[-1]
    assert name == "done"
    assert metrics["completion_tokens"] == 2
    assert {"total_ms", "ttft_ms", "tokens_per_second"} <= metrics.keys()
    assert provider.received[0].content == "Salut"


def test_chat_reports_provider_failure_inside_the_stream(client, use_provider):
    use_provider(FakeProvider([TokenEvent(content="Bon")], fail=True))

    response = client.post("/api/chat", json=CHAT_BODY)

    events = parse_sse(response.text)
    assert events[0] == ("token", {"content": "Bon"})
    assert events[-1] == ("error", {"message": "fake: connection lost"})


def test_chat_rejects_empty_conversation(client, use_provider):
    use_provider(FakeProvider())

    response = client.post("/api/chat", json={"model": "fake-model", "messages": []})

    assert response.status_code == 422
