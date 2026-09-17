import asyncio

import httpx
import pytest
from conftest import FakeProvider
from sqlalchemy.ext.asyncio import async_sessionmaker

from netherbrain.api.deps import get_session_factory
from netherbrain.db.session import create_engine
from netherbrain.main import app
from netherbrain.providers import OllamaProvider
from netherbrain.providers.catalog import (
    card_from_ollama,
    card_from_openai_compatible,
    parse_billions,
)
from netherbrain.schemas import TokenEvent, UsageEvent

# Extraits de réponses réelles d'Ollama (GET /api/tags) et d'OpenRouter (GET /models).
OLLAMA_QWEN = {
    "name": "qwen3:8b",
    "size": 5225388164,
    "details": {
        "family": "qwen3",
        "parameter_size": "8.2B",
        "quantization_level": "Q4_K_M",
        "context_length": 40960,
    },
    "capabilities": ["completion", "tools", "thinking"],
}
OLLAMA_EMBEDDING = {
    "name": "nomic-embed-text:latest",
    "size": 274302450,
    "details": {"family": "nomic-bert", "parameter_size": "137M"},
    "capabilities": ["embedding"],
}
OPENROUTER_GEMMA = {
    "name": "Google: Gemma 4 31B (free)",
    "description": "Gemma 4 31B Instruct is Google DeepMind's 30.7B dense multimodal model.",
    "context_length": 262144,
    "architecture": {"input_modalities": ["image", "text", "video"], "output_modalities": ["text"]},
    "supported_parameters": ["include_reasoning", "reasoning", "tools", "temperature"],
    "pricing": {"prompt": "0", "completion": "0"},
}


# --- Construction des fiches ---


def test_an_ollama_model_card():
    card = card_from_ollama("ollama", OLLAMA_QWEN)

    assert card.local is True
    assert card.parameters_b == 8.2
    assert card.context_length == 40960
    assert card.quantization == "Q4_K_M"
    assert card.capabilities == ["reasoning", "tools"]
    assert card.description is not None


def test_an_ollama_embedding_model_is_flagged():
    card = card_from_ollama("ollama", OLLAMA_EMBEDDING)

    assert card.capabilities == ["embedding"]
    assert "not for chat" in card.description


def test_an_openrouter_model_card():
    card = card_from_openai_compatible("openrouter", "google/gemma-4-31b-it:free", OPENROUTER_GEMMA)

    assert card.name == "Google: Gemma 4 31B (free)"
    assert card.local is False
    assert card.parameters_b == 31
    assert card.context_length == 262144
    assert set(card.capabilities) == {"reasoning", "tools", "vision"}
    assert card.free is True


def test_a_minimal_openai_compatible_model_card():
    card = card_from_openai_compatible("groq", "qwen/qwen3-coder-32b", {"context_window": 131072})

    assert card.context_length == 131072
    assert card.capabilities == ["code"]
    assert card.free is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("8.2B", 8.2),
        ("nvidia/nemotron-3-super-120b-a12b:free", 120),
        ("gpt-oss:20b", 20),
        ("137M", None),
        (None, None),
    ],
)
def test_parse_billions(text, expected):
    assert parse_billions(text) == expected


def test_ollama_offers_only_chat_models_to_the_chat():
    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        return httpx.Response(200, json={"models": [OLLAMA_QWEN, OLLAMA_EMBEDDING]})

    provider = OllamaProvider("http://ollama.test:11434/v1", transport=httpx.MockTransport(handler))

    assert asyncio.run(provider.list_models()) == ["qwen3:8b"]
    assert requested == ["/api/tags"]


# --- Route /api/catalog ---


def test_the_catalog_merges_cards_with_measured_stats(client, use_providers):
    events = [TokenEvent(content="ok"), UsageEvent(prompt_tokens=1, completion_tokens=10)]
    use_providers(FakeProvider("gpu", local=True, events=events), FakeProvider("cloud"))
    # Une réponse dans le chat…
    conversation_id = client.post("/api/conversations").json()["id"]
    client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"provider": "gpu", "model": "gpu-model", "content": "Salut"},
    )
    # … et une dans une comparaison : les deux comptent.
    comparison = client.post(
        "/api/comparisons",
        json={
            "prompt": "Question",
            "contenders": [
                {"provider": "gpu", "model": "gpu-model"},
                {"provider": "cloud", "model": "cloud-model"},
            ],
        },
    ).json()
    client.post(f"/api/comparisons/{comparison['id']}/results/{comparison['results'][0]['id']}/run")

    body = client.get("/api/catalog").json()

    cards = {card["id"]: card for card in body["models"]}
    assert set(cards) == {"gpu-model", "cloud-model"}
    assert cards["gpu-model"]["local"] is True
    assert cards["gpu-model"]["stats"]["answers"] == 2
    assert cards["gpu-model"]["stats"]["avg_tokens_per_second"] is not None
    assert cards["cloud-model"]["stats"] is None
    assert body["stats_available"] is True


def test_the_catalog_still_answers_when_the_database_is_down(client, use_providers):
    use_providers(FakeProvider("gpu"))
    engine = create_engine("postgresql+asyncpg://user:secret@127.0.0.1:1/netherbrain")
    app.dependency_overrides[get_session_factory] = lambda: async_sessionmaker(engine)

    response = client.get("/api/catalog")

    assert response.status_code == 200
    assert response.json()["stats_available"] is False
    assert [card["id"] for card in response.json()["models"]] == ["gpu-model"]
