import asyncio
import json

import httpx
import openai
import pytest

from netherbrain.api.deps import build_registry
from netherbrain.config import Settings
from netherbrain.providers import OllamaProvider, ProviderError
from netherbrain.providers.filters import is_free_openrouter_model, is_groq_chat_model
from netherbrain.providers.openai_compatible import describe_error
from netherbrain.schemas import (
    ChatMessage,
    ReasoningEvent,
    TokenEvent,
    ToolCallEvent,
    UsageEvent,
)

REQUEST = httpx.Request("POST", "http://provider.test/v1/chat/completions")


def status_error(error_class, status: int, body: dict) -> openai.APIStatusError:
    return error_class("raw message", response=httpx.Response(status, request=REQUEST), body=body)


def make_settings(**overrides) -> Settings:
    # _env_file=None : ignore le vrai .env du développeur, pour des tests reproductibles.
    return Settings(_env_file=None, **overrides)


def test_only_ollama_is_enabled_without_api_keys():
    assert build_registry(make_settings()).names == ["ollama"]


def test_remote_providers_are_enabled_by_their_api_key():
    settings = make_settings(openrouter_api_key="sk-or-test", groq_api_key="gsk-test")

    assert build_registry(settings).names == ["ollama", "openrouter", "groq"]


def test_only_ollama_runs_locally():
    registry = build_registry(make_settings(openrouter_api_key="sk-or-test"))

    assert registry.get("ollama").local is True
    assert registry.get("openrouter").local is False


def test_an_empty_api_key_leaves_the_provider_disabled():
    assert build_registry(make_settings(groq_api_key="")).names == ["ollama"]


def test_api_keys_never_appear_in_settings_repr():
    settings = make_settings(openrouter_api_key="sk-or-test")

    assert "sk-or-test" not in repr(settings)
    assert settings.openrouter_api_key.get_secret_value() == "sk-or-test"


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("google/gemma-4-31b-it:free", True),
        ("google/gemma-4-31b-it", False),
        ("deepseek/deepseek-r1", False),
    ],
)
def test_openrouter_free_filter(model_id, expected):
    assert is_free_openrouter_model(model_id) is expected


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("llama-3.3-70b-versatile", True),
        ("qwen/qwen3-32b", True),
        ("whisper-large-v3", False),
        ("playai-tts", False),
        ("meta-llama/llama-guard-4-12b", False),
    ],
)
def test_groq_chat_filter(model_id, expected):
    assert is_groq_chat_model(model_id) is expected


def test_a_rate_limit_gets_a_short_explanation_without_account_details():
    body = {
        "error": {"message": "Provider returned error", "metadata": {"raw": "a very long text"}},
        "user_id": "user_123",
    }

    message = describe_error(status_error(openai.RateLimitError, 429, body))

    assert "rate limit" in message
    assert "user_123" not in message


def test_an_http_error_keeps_only_the_provider_message():
    body = {"error": {"message": "model 'nope' not found", "type": "not_found_error"}}

    message = describe_error(status_error(openai.NotFoundError, 404, body))

    assert message == "HTTP 404: model 'nope' not found"


def test_a_network_error_is_described_plainly():
    assert describe_error(openai.APIConnectionError(request=REQUEST)) == "Connection error."


# --- Ollama : l'API native, seule à accepter la taille du contexte ---


def collect(stream) -> list:
    async def drain() -> list:
        return [event async for event in stream]

    return asyncio.run(drain())


def ollama_stream(*lines: dict) -> httpx.MockTransport:
    """Un faux Ollama qui rejoue des morceaux de stream, une ligne de JSON chacun."""
    body = "\n".join(json.dumps(line) for line in lines)
    return httpx.MockTransport(lambda request: httpx.Response(200, text=body))


def test_ollama_streams_thinking_content_and_tool_calls():
    transport = ollama_stream(
        {"message": {"role": "assistant", "thinking": "Hmm"}, "done": False},
        {"message": {"role": "assistant", "content": "Bonjour"}, "done": False},
        {
            "message": {
                "role": "assistant",
                "tool_calls": [
                    {"id": "call_7", "function": {"name": "read_file", "arguments": {"path": "a"}}}
                ],
            },
            "done": False,
        },
        {
            "message": {"role": "assistant", "content": ""},
            "done": True,
            "prompt_eval_count": 12,
            "eval_count": 3,
        },
    )
    provider = OllamaProvider("http://ollama.test:11434/v1", transport=transport)

    events = collect(provider.stream_chat("m", [ChatMessage(role="user", content="salut")]))

    assert events == [
        ReasoningEvent(content="Hmm"),
        TokenEvent(content="Bonjour"),
        ToolCallEvent(id="call_7", name="read_file", arguments='{"path": "a"}'),
        UsageEvent(prompt_tokens=12, completion_tokens=3),
    ]


def test_ollama_asks_for_a_context_window_and_converts_tool_calls():
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, text=json.dumps({"message": {"content": "ok"}, "done": True}))

    provider = OllamaProvider(
        "http://ollama.test:11434/v1",
        context_length=8192,
        transport=httpx.MockTransport(handler),
    )
    history = [
        ChatMessage(
            role="assistant",
            content="",
            tool_calls=[
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "a"}'},
                }
            ],
        ),
        ChatMessage(role="tool", content="contenu du fichier", tool_call_id="c1"),
    ]

    collect(provider.stream_chat("m", history, tools=[{"type": "function"}]))

    assert sent[0]["options"] == {"num_ctx": 8192}
    assert sent[0]["tools"] == [{"type": "function"}]
    # Les arguments repartent en objet JSON, comme l'attend l'API native.
    assert sent[0]["messages"][0]["tool_calls"][0]["function"]["arguments"] == {"path": "a"}
    assert sent[0]["messages"][1] == {"role": "tool", "content": "contenu du fichier"}


def test_an_unreachable_ollama_is_reported():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    provider = OllamaProvider("http://ollama.test:11434/v1", transport=httpx.MockTransport(refuse))

    with pytest.raises(ProviderError, match="not running"):
        collect(provider.stream_chat("m", [ChatMessage(role="user", content="salut")]))


# --- Sortie structurée ---


def test_ollama_structured_output_follows_the_schema():
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(
            200, json={"message": {"role": "assistant", "content": '{"tasks": ["code"]}'}}
        )

    provider = OllamaProvider(
        "http://ollama.test:11434/v1", context_length=8192, transport=httpx.MockTransport(handler)
    )
    schema = {"type": "object"}

    answer = asyncio.run(
        provider.complete_json(
            "m", [ChatMessage(role="user", content="salut")], schema, think=False
        )
    )

    assert answer == {"tasks": ["code"]}
    assert (sent[0]["format"], sent[0]["stream"], sent[0]["think"]) == (schema, False, False)
    assert sent[0]["options"] == {"temperature": 0, "num_ctx": 8192}


def test_an_answer_that_is_not_json_is_an_error():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"message": {"content": "pas du json"}})
    )
    provider = OllamaProvider("http://ollama.test:11434/v1", transport=transport)

    with pytest.raises(ProviderError, match="not valid JSON"):
        asyncio.run(provider.complete_json("m", [ChatMessage(role="user", content="x")], {}))
