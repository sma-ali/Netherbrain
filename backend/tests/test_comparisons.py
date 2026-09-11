import pytest
from conftest import FakeProvider, parse_sse

from netherbrain.schemas import TokenEvent, UsageEvent

MISSING_ID = "01a09034-355e-71a4-8403-8a1b1710aa0f"
TWO_MODELS = [("fast", "fast-model"), ("slow", "slow-model")]


def create(client, prompt: str = "Question ?", contenders=TWO_MODELS):
    return client.post(
        "/api/comparisons",
        json={
            "prompt": prompt,
            "contenders": [{"provider": p, "model": m} for p, m in contenders],
        },
    )


def run(client, comparison_id: str, result_id: str):
    return client.post(f"/api/comparisons/{comparison_id}/results/{result_id}/run")


@pytest.fixture
def providers(use_providers):
    fast = FakeProvider(
        "fast",
        events=[TokenEvent(content="Rapide"), UsageEvent(prompt_tokens=2, completion_tokens=1)],
    )
    slow = FakeProvider("slow", events=[TokenEvent(content="Lent")])
    use_providers(fast, slow)
    return fast, slow


def test_creating_a_comparison_prepares_one_pending_result_per_model(client, providers):
    response = create(client)

    assert response.status_code == 201
    results = response.json()["results"]
    assert [(r["position"], r["provider"], r["state"]) for r in results] == [
        (0, "fast", "pending"),
        (1, "slow", "pending"),
    ]
    assert client.get("/api/comparisons").json()[0]["models"] == ["fast-model", "slow-model"]


def test_running_a_result_streams_and_saves_the_answer(client, providers):
    fast, _ = providers
    comparison = create(client, prompt="Qui est le plus rapide ?").json()

    response = run(client, comparison["id"], comparison["results"][0]["id"])

    assert [name for name, _ in parse_sse(response.text)] == ["token", "done"]
    assert [(m.role, m.content) for m in fast.received] == [("user", "Qui est le plus rapide ?")]
    saved = client.get(f"/api/comparisons/{comparison['id']}").json()["results"][0]
    assert (saved["state"], saved["content"]) == ("done", "Rapide")
    assert saved["metrics"]["completion_tokens"] == 1


def test_an_answer_cannot_be_generated_twice(client, providers):
    comparison = create(client).json()
    result_id = comparison["results"][0]["id"]

    run(client, comparison["id"], result_id)

    assert run(client, comparison["id"], result_id).status_code == 409


def test_a_failing_model_is_saved_as_an_error_with_its_partial_answer(client, use_providers):
    use_providers(
        FakeProvider("fast", events=[TokenEvent(content="Dé")], fail=True), FakeProvider("slow")
    )
    comparison = create(client).json()

    run(client, comparison["id"], comparison["results"][0]["id"])

    saved = client.get(f"/api/comparisons/{comparison['id']}").json()["results"][0]
    assert (saved["state"], saved["content"], saved["error"]) == (
        "error",
        "Dé",
        "fast: connection lost",
    )


def test_a_comparison_needs_two_to_four_models(client, providers):
    assert create(client, contenders=[("fast", "fast-model")]).status_code == 422
    assert create(client, contenders=[("fast", f"model-{i}") for i in range(5)]).status_code == 422


def test_an_unknown_provider_is_refused_and_nothing_is_saved(client, providers):
    assert create(client, contenders=[("fast", "fast-model"), ("nope", "x")]).status_code == 404
    assert client.get("/api/comparisons").json() == []


def test_deleting_a_comparison(client, providers):
    comparison = create(client).json()

    assert client.delete(f"/api/comparisons/{comparison['id']}").status_code == 204
    assert client.get(f"/api/comparisons/{comparison['id']}").status_code == 404


def test_an_unknown_comparison_or_result_returns_404(client, providers):
    comparison = create(client).json()

    assert client.get(f"/api/comparisons/{MISSING_ID}").status_code == 404
    assert client.delete(f"/api/comparisons/{MISSING_ID}").status_code == 404
    assert run(client, comparison["id"], MISSING_ID).status_code == 404
    assert run(client, MISSING_ID, comparison["results"][0]["id"]).status_code == 404
