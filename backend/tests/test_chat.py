from conftest import FakeProvider, parse_sse

from netherbrain.schemas import ReasoningEvent, TokenEvent, UsageEvent

CHAT_BODY = {
    "provider": "fake",
    "model": "fake-model",
    "messages": [{"role": "user", "content": "Salut"}],
}


# --- /api/models ---


def test_models_are_aggregated_across_providers(client, use_providers):
    use_providers(FakeProvider("local", ["a", "b"]), FakeProvider("remote", ["c"]))

    body = client.get("/api/models").json()

    assert body["models"] == [
        {"id": "a", "provider": "local", "tools": False},
        {"id": "b", "provider": "local", "tools": False},
        {"id": "c", "provider": "remote", "tools": False},
    ]
    assert [p["available"] for p in body["providers"]] == [True, True]


def test_a_failing_provider_does_not_hide_the_others(client, use_providers):
    use_providers(FakeProvider("local"), FakeProvider("remote", fail=True))

    response = client.get("/api/models")

    assert response.status_code == 200
    body = response.json()
    assert body["models"] == [{"id": "local-model", "provider": "local", "tools": False}]
    assert body["providers"] == [
        {"name": "local", "local": False, "available": True, "error": None},
        {"name": "remote", "local": False, "available": False, "error": "remote: unreachable"},
    ]


def test_local_providers_are_flagged(client, use_providers):
    use_providers(FakeProvider("gpu", local=True), FakeProvider("cloud"))

    providers = client.get("/api/models").json()["providers"]

    assert {p["name"]: p["local"] for p in providers} == {"gpu": True, "cloud": False}


def test_a_slow_provider_is_marked_unavailable(client, use_providers):
    use_providers(FakeProvider("local"), FakeProvider("slow", list_delay=1), list_timeout=0.05)

    body = client.get("/api/models").json()

    assert [m["provider"] for m in body["models"]] == ["local"]
    slow = body["providers"][1]
    assert slow["available"] is False
    assert "0.05s" in slow["error"]


# --- /api/chat ---


def test_chat_streams_reasoning_tokens_then_metrics(client, use_providers):
    provider = FakeProvider(
        events=[
            ReasoningEvent(content="Hmm..."),
            TokenEvent(content="Bon"),
            TokenEvent(content="jour"),
            UsageEvent(prompt_tokens=5, completion_tokens=2),
        ]
    )
    use_providers(provider)

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


def test_chat_routes_to_the_requested_provider(client, use_providers):
    local = FakeProvider("local", events=[TokenEvent(content="from local")])
    remote = FakeProvider("remote", events=[TokenEvent(content="from remote")])
    use_providers(local, remote)

    response = client.post("/api/chat", json={**CHAT_BODY, "provider": "remote"})

    assert parse_sse(response.text)[0] == ("token", {"content": "from remote"})
    assert remote.received and not local.received


def test_chat_with_an_unknown_provider_returns_404(client, use_providers):
    use_providers(FakeProvider("local"))

    response = client.post("/api/chat", json={**CHAT_BODY, "provider": "nope"})

    assert response.status_code == 404
    assert "local" in response.json()["detail"]


def test_chat_reports_provider_failure_inside_the_stream(client, use_providers):
    use_providers(FakeProvider(events=[TokenEvent(content="Bon")], fail=True))

    response = client.post("/api/chat", json=CHAT_BODY)

    events = parse_sse(response.text)
    assert events[0] == ("token", {"content": "Bon"})
    assert events[-1] == ("error", {"message": "fake: connection lost"})


def test_chat_rejects_empty_conversation(client, use_providers):
    use_providers(FakeProvider())

    response = client.post("/api/chat", json={**CHAT_BODY, "messages": []})

    assert response.status_code == 422
