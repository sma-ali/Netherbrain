"""Le conseiller : comprendre la demande, retrouver les benchmarks, classer les modèles."""

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from conftest import FakeProvider
from sqlalchemy import update

from netherbrain.advisor.knowledge import profile_for
from netherbrain.advisor.matching import BenchmarkIndex, words
from netherbrain.advisor.needs import needs_from_keywords
from netherbrain.advisor.scoring import Candidate, recommend_models
from netherbrain.advisor.sources import ArtificialAnalysisClient, BenchmarkEntry, BenchmarkError
from netherbrain.advisor.sync import is_stale
from netherbrain.advisor.understand import pick_advisor_model
from netherbrain.api.deps import get_benchmarks_client
from netherbrain.config import Settings, get_settings
from netherbrain.db.models import ModelBenchmark
from netherbrain.main import app
from netherbrain.providers import OllamaProvider, ProviderResult
from netherbrain.schemas import ModelCard, Needs


def entry(name: str, **scores) -> BenchmarkEntry:
    slug = name.lower().replace(" ", "-").replace(".", "-")
    return BenchmarkEntry(source_id=name, name=name, slug=slug, **scores)


def candidate(
    model: str,
    *,
    capabilities=(),
    size_gb: float | None = 5.0,
    local: bool = True,
    ready: bool = True,
    context: int = 131_072,
    tps: float | None = None,
    index: BenchmarkIndex | None = None,
) -> Candidate:
    return Candidate(
        model=model,
        provider=None if not ready else "ollama" if local else "openrouter",
        local=local,
        ready=ready,
        capabilities=set(capabilities),
        size_gb=size_gb,
        context_length=context,
        free=True,
        measured_tps=tps,
        profile=profile_for(model),
        benchmark=index.match(model) if index else None,
    )


def models_of(picks) -> list[str]:
    return [scored.candidate.model for _, scored in picks]


CODE = Needs(tasks=["code"])


# --- Comprendre la demande par mots-clés ---


def test_keywords_understand_a_simple_request():
    needs = needs_from_keywords("Un bot Discord qui résume des PDF en français, en local")

    assert {"summary", "multilingual"} <= set(needs.tasks)
    assert "long_context" in needs.requires
    assert needs.local_only is True


def test_keywords_must_start_a_word():
    # « rapide » contient « api », qui ne doit pas faire croire à du code.
    needs = needs_from_keywords("Je veux un assistant rapide")

    assert "code" not in needs.tasks
    assert needs.priority == "speed"


def test_without_any_keyword_it_is_a_chat():
    assert needs_from_keywords("bonjour à toi").tasks == ["chat"]


def test_some_tasks_imply_a_capability():
    # Le LLM a compris « vision » mais oublié de l'exiger : le code la rajoute.
    needs = Needs.model_validate({"tasks": ["vision", "agent"], "requires": []})

    assert needs.requires == ["vision", "tools"]


def test_needs_are_deduplicated_and_limited_to_three_tasks():
    needs = Needs.model_validate({"tasks": ["code", "code", "chat", "writing", "summary"]})

    assert needs.tasks == ["code", "chat", "writing"]


# --- Retrouver un modèle dans les benchmarks ---

BENCHMARKED = BenchmarkIndex(
    [
        entry("Qwen3.5 9B"),
        entry("DeepSeek R1 Distill Qwen 14B"),
        entry("Gemma 4 12B"),
        entry("Qwen3 8B"),
        entry("Qwen3 VL 8B"),
        entry("Qwen3 14B"),
    ]
)


def test_names_are_split_into_comparable_words():
    assert words("qwen3.5:9b-q4_K_M") == ["qwen3", "5", "9b"]
    assert words("Gemma 4 12B Instruct") == words("gemma4:12b") == ["gemma4", "12b"]


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("qwen3.5:9b", "Qwen3.5 9B"),
        ("qwen/qwen3.5-9b:free", "Qwen3.5 9B"),
        ("deepseek-r1:14b", "DeepSeek R1 Distill Qwen 14B"),
        ("gemma4:12b", "Gemma 4 12B"),
        ("qwen3:8b", "Qwen3 8B"),  # et pas sa variante vision, « Qwen3 VL 8B »
    ],
)
def test_models_are_found_despite_different_names(model, expected):
    match = BENCHMARKED.match(model)

    assert match is not None
    assert match.name == expected


@pytest.mark.parametrize("model", ["qwen3:4b", "llama3.1:8b", "qwen3"])
def test_no_match_rather_than_a_wrong_one(model):
    assert BENCHMARKED.match(model) is None


def test_percentiles_say_how_many_models_are_beaten():
    index = BenchmarkIndex([entry(f"Model {n}B", coding=n * 10) for n in (1, 2, 3, 4)])

    assert index.match("model:3b").percentiles == {"coding": 0.5}


# --- L'API d'Artificial Analysis ---


def test_artificial_analysis_models_are_read():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(key=request.headers.get("x-api-key"), url=str(request.url))
        return httpx.Response(
            200,
            json={
                "status": 200,
                "data": [
                    {
                        "id": "1",
                        "name": "Qwen3.5 9B",
                        "slug": "qwen3-5-9b",
                        "model_creator": {"name": "Alibaba"},
                        "evaluations": {
                            "artificial_analysis_intelligence_index": 38.5,
                            "artificial_analysis_coding_index": 30.1,
                            "artificial_analysis_math_index": None,
                        },
                        "median_output_tokens_per_second": 120,
                    },
                    {"name": "sans identifiant"},
                ],
            },
        )

    client = ArtificialAnalysisClient("aa-secret", transport=httpx.MockTransport(handler))

    [model] = asyncio.run(client.fetch())

    assert seen == {
        "key": "aa-secret",
        "url": "https://artificialanalysis.ai/api/v2/data/llms/models",
    }
    assert (model.name, model.creator, model.coding, model.math, model.output_speed) == (
        "Qwen3.5 9B",
        "Alibaba",
        30.1,
        None,
        120.0,
    )


@pytest.mark.parametrize(
    ("status", "message"), [(401, "refused the API key"), (429, "limit"), (500, "HTTP 500")]
)
def test_artificial_analysis_errors_are_explained(status, message):
    transport = httpx.MockTransport(lambda request: httpx.Response(status))
    client = ArtificialAnalysisClient("key", transport=transport)

    with pytest.raises(BenchmarkError, match=message):
        asyncio.run(client.fetch())


def test_benchmarks_older_than_a_day_are_stale():
    now = datetime(2026, 9, 16, 12, tzinfo=UTC)

    assert is_stale(None, 24, now=now)
    assert not is_stale(now - timedelta(hours=2), 24, now=now)
    assert is_stale(now - timedelta(hours=30), 24, now=now)
    # SQLite rend les dates sans fuseau horaire : elles sont en UTC.
    assert not is_stale((now - timedelta(hours=2)).replace(tzinfo=None), 24, now=now)


# --- Le classement ---


def test_the_grid_puts_a_coding_model_first_for_code():
    picks = recommend_models(
        CODE, [candidate("gemma4:12b", size_gb=7.6), candidate("ornith:9b", size_gb=5.6)], 16
    )

    assert picks[0][0] == "best"
    assert models_of(picks) == ["ornith:9b"]
    assert "Code: 5/5 in Netherbrain's model grid" in picks[0][1].reasons


def test_required_capabilities_are_mandatory():
    needs = Needs(tasks=["vision"], requires=["vision"])
    candidates = [
        candidate("ornith:9b", capabilities=["tools"]),
        candidate("gemma4:12b", capabilities=["vision"], size_gb=7.6),
    ]

    assert models_of(recommend_models(needs, candidates, 16)) == ["gemma4:12b"]


def test_local_only_leaves_the_cloud_out():
    needs = Needs(tasks=["chat"], local_only=True)
    candidates = [candidate("qwen3:8b"), candidate("glm-5.3", local=False, size_gb=None)]

    assert models_of(recommend_models(needs, candidates, 16)) == ["qwen3:8b"]


def test_the_priority_decides_between_quality_and_speed():
    candidates = [
        candidate("deepseek-r1:14b", size_gb=9.0, tps=40),
        candidate("qwen3:8b", size_gb=5.2, tps=110),
    ]

    quality = recommend_models(Needs(tasks=["reasoning"], priority="quality"), candidates, 16)
    speed = recommend_models(Needs(tasks=["reasoning"], priority="speed"), candidates, 16)

    assert [(role, s.candidate.model) for role, s in quality] == [
        ("best", "deepseek-r1:14b"),
        ("fastest", "qwen3:8b"),
    ]
    assert speed[0][1].candidate.model == "qwen3:8b"


def test_benchmarks_can_overturn_the_grid():
    index = BenchmarkIndex(
        [
            entry("Gemma 4 12B", coding=45),
            entry("Ornith 9B", coding=10),
            *[entry(f"Other {n}B", coding=n) for n in range(20, 40)],
        ]
    )
    candidates = [
        candidate("gemma4:12b", size_gb=7.6, index=index),
        candidate("ornith:9b", size_gb=5.6, index=index),
    ]

    [(_, best)] = recommend_models(CODE, candidates, 16)

    assert best.candidate.model == "gemma4:12b"
    assert any("better than 95%" in reason for reason in best.reasons)


def test_a_better_model_is_suggested_for_download_when_it_fits():
    candidates = [
        candidate("gemma4:12b", size_gb=7.6),
        candidate("devstral:24b", ready=False, size_gb=14.0),
    ]

    picks = recommend_models(CODE, candidates, 16)

    assert dict((role, s.candidate.model) for role, s in picks)["download"] == "devstral:24b"
    assert models_of(recommend_models(CODE, candidates, 8)) == ["gemma4:12b"]


def test_long_documents_need_a_long_context():
    needs = Needs(tasks=["summary"], requires=["long_context"])
    candidates = [candidate("phi4:14b", context=16_384), candidate("llama3.1:8b")]

    [(_, best), *_] = recommend_models(needs, candidates, 16)

    assert best.candidate.model == "llama3.1:8b"


# --- La route /api/advisor ---


class FakeBenchmarks:
    """Remplace l'API d'Artificial Analysis : des modèles préparés, ou une erreur."""

    def __init__(self, entries: list[BenchmarkEntry] | None = None, error: str | None = None):
        self.entries = entries or []
        self.error = error
        self.calls = 0

    async def fetch(self) -> list[BenchmarkEntry]:
        self.calls += 1
        if self.error:
            raise BenchmarkError(self.error)
        return self.entries


BENCHMARKS = [entry("Gemma 4 12B", intelligence=40, coding=45), entry("Other 20B", coding=10)]


def use_settings(**overrides) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, **overrides)


def use_benchmarks(benchmarks: FakeBenchmarks) -> FakeBenchmarks:
    app.dependency_overrides[get_benchmarks_client] = lambda: benchmarks
    return benchmarks


def local_models(**fields) -> FakeProvider:
    return FakeProvider(
        "ollama", models=["ornith:9b", "gemma4:12b"], local=True, capabilities=["tools"], **fields
    )


def recommend(client, query: str = "Je veux coder une API en Python"):
    return client.post("/api/advisor/recommend", json={"query": query})


async def age_benchmarks(session_factory) -> None:
    async with session_factory() as session:
        old = datetime.now(UTC) - timedelta(days=3)
        await session.execute(update(ModelBenchmark).values(fetched_at=old))
        await session.commit()


def test_a_model_reads_the_request_before_the_ranking(client, use_providers):
    use_settings()
    provider = local_models(
        json_reply={"tasks": ["code", "agent"], "requires": ["tools"], "local_only": True}
    )
    use_providers(provider)

    response = recommend(client)

    assert response.status_code == 200
    body = response.json()
    assert body["understood_by"] == "gemma4:12b"
    assert body["needs"]["tasks"] == ["code", "agent"]
    assert (body["picks"][0]["role"], body["picks"][0]["model"]) == ("best", "ornith:9b")
    assert all(pick["local"] for pick in body["picks"])
    # Le modèle reçoit la demande, et le schéma JSON qu'il doit respecter.
    _, messages, schema, _ = provider.json_requests[0]
    assert messages[-1].content == "Je veux coder une API en Python"
    assert "tasks" in schema["properties"]


def test_without_structured_output_keywords_take_over(client, use_providers):
    use_settings()
    use_providers(local_models())  # sans json_reply : la sortie structurée échoue

    body = recommend(client).json()

    assert body["understood_by"] == "keywords"
    assert "code" in body["needs"]["tasks"]
    assert body["picks"]


def test_uninstalled_models_come_with_their_download_command(client, use_providers):
    use_settings()
    use_providers(local_models(json_reply={"tasks": ["reasoning"]}))

    picks = recommend(client).json()["picks"]

    download = next(pick for pick in picks if pick["role"] == "download")
    assert download["ready"] is False
    assert download["pull_command"] == f"ollama pull {download['model']}"


def test_without_ollama_local_models_are_left_out(client, use_providers):
    use_settings()
    use_providers(
        FakeProvider("ollama", local=True, fail=True),
        FakeProvider("openrouter", models=["qwen/qwen3.5-9b:free"]),
    )

    body = recommend(client, "Écrire des articles de blog").json()

    assert "Ollama is not running" in body["warnings"][0]
    assert [(pick["model"], pick["local"]) for pick in body["picks"]] == [
        ("qwen/qwen3.5-9b:free", False)
    ]


def test_a_request_too_short_is_refused(client, use_providers):
    use_providers(local_models())

    assert recommend(client, "?").status_code == 422


def test_live_benchmarks_are_off_without_a_key(client, use_providers):
    use_settings()
    use_providers(local_models())

    benchmarks = client.get("/api/advisor/benchmarks").json()

    assert (benchmarks["configured"], benchmarks["models"], benchmarks["url"]) == (
        False,
        0,
        "https://artificialanalysis.ai/",
    )
    assert client.post("/api/advisor/benchmarks/sync").status_code == 400


def test_benchmarks_are_fetched_stored_and_used(client, use_providers):
    use_settings()
    use_providers(local_models(json_reply={"tasks": ["writing", "multilingual"]}))
    benchmarks = use_benchmarks(FakeBenchmarks(BENCHMARKS))

    synced = client.post("/api/advisor/benchmarks/sync").json()
    body = recommend(client).json()

    assert (synced["configured"], synced["models"]) == (True, 2)
    assert synced["fetched_at"] is not None
    assert benchmarks.calls == 1  # déjà en base et récents : pas de nouvel appel
    best = body["picks"][0]
    assert (best["model"], best["benchmark"]) == ("gemma4:12b", "Gemma 4 12B")
    assert any("Artificial Analysis" in reason for reason in best["reasons"])


def test_the_first_advice_fetches_the_benchmarks(client, use_providers):
    use_settings()
    use_providers(local_models())
    benchmarks = use_benchmarks(FakeBenchmarks(BENCHMARKS))

    body = recommend(client).json()

    assert benchmarks.calls == 1
    assert body["benchmarks"]["models"] == 2


def test_stale_benchmarks_are_refreshed_in_the_background(client, use_providers):
    use_settings()
    use_providers(local_models())
    benchmarks = use_benchmarks(FakeBenchmarks(BENCHMARKS))
    client.post("/api/advisor/benchmarks/sync")
    client.portal.call(age_benchmarks, client.session_factory)

    recommend(client)

    # Avec TestClient, la tâche de fond est finie quand la requête rend la main.
    assert benchmarks.calls == 2


def test_a_benchmark_failure_does_not_block_the_advice(client, use_providers):
    use_settings()
    use_providers(local_models())
    use_benchmarks(FakeBenchmarks(error="Artificial Analysis refused the API key"))

    body = recommend(client).json()

    assert body["picks"]
    assert body["benchmarks"]["error"] == "Artificial Analysis refused the API key"
    assert client.post("/api/advisor/benchmarks/sync").status_code == 502


# --- Lecture rapide, et choix du modèle qui lit la demande ---


def test_a_quick_read_skips_the_model(client, use_providers):
    use_settings()
    provider = local_models(json_reply={"tasks": ["writing"]})
    use_providers(provider)

    response = client.post(
        "/api/advisor/recommend", json={"query": "Coder une API en Python", "understand": False}
    )

    assert response.json()["understood_by"] == "keywords"
    assert provider.json_requests == []


def test_a_model_already_in_memory_reads_the_request():
    cards = [
        ModelCard(id="qwen3.5:9b", provider="ollama", local=True, name="qwen3.5:9b"),
        ModelCard(id="ornith:9b", provider="ollama", local=True, name="ornith:9b"),
    ]
    results = [ProviderResult("ollama", local=True, items=cards)]

    assert pick_advisor_model(results, None).model == "qwen3.5:9b"
    assert pick_advisor_model(results, None, frozenset({"ornith:9b"})).model == "ornith:9b"
    assert pick_advisor_model(results, "openrouter/some-model").provider == "openrouter"


def test_ollama_says_which_models_are_loaded():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"models": [{"name": "qwen3:8b"}]})
    )
    provider = OllamaProvider("http://ollama.test:11434/v1", transport=transport)

    assert asyncio.run(provider.loaded_models()) == ["qwen3:8b"]
    down = OllamaProvider(
        "http://ollama.test:11434/v1",
        transport=httpx.MockTransport(lambda request: httpx.Response(500)),
    )
    assert asyncio.run(down.loaded_models()) == []
