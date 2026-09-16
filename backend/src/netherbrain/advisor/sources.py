"""Les benchmarks publics en ligne : Artificial Analysis et son API gratuite.

Artificial Analysis évalue en continu les modèles du marché (indices d'intelligence, de code
et de maths, vitesse chez les fournisseurs). L'API demande une clé gratuite, limite à 1 000
requêtes par jour et impose de citer la source : on garde donc les résultats en base, et on
ne la rappelle qu'une fois par jour au plus.
"""

import math
from dataclasses import dataclass
from typing import Any

import httpx

SOURCE = "artificial_analysis"
SOURCE_NAME = "Artificial Analysis"
SOURCE_URL = "https://artificialanalysis.ai/"


class BenchmarkError(Exception):
    """Les benchmarks n'ont pas pu être récupérés ; le message s'affiche tel quel."""


@dataclass(frozen=True)
class BenchmarkEntry:
    source_id: str
    name: str
    slug: str
    creator: str | None = None
    # Indices sur 100 d'Artificial Analysis ; None quand le modèle n'a pas été évalué.
    intelligence: float | None = None
    coding: float | None = None
    math: float | None = None
    # Vitesse médiane de génération chez les fournisseurs d'API, en tokens par seconde.
    output_speed: float | None = None

    def scores(self) -> dict[str, float | None]:
        return {
            "intelligence": self.intelligence,
            "coding": self.coding,
            "math": self.math,
            "output_speed": self.output_speed,
        }


class ArtificialAnalysisClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://artificialanalysis.ai/api/v2",
        *,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._url = base_url.rstrip("/") + "/data/llms/models"
        self._timeout = timeout
        # Les tests remplacent le réseau par des réponses préparées à l'avance.
        self._transport = transport

    async def fetch(self) -> list[BenchmarkEntry]:
        """Tous les modèles évalués, avec leurs indices."""
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                # La clé reste côté serveur : elle ne doit jamais partir vers le navigateur.
                response = await client.get(self._url, headers={"x-api-key": self._api_key})
        except httpx.HTTPError as exc:
            detail = str(exc) or type(exc).__name__
            raise BenchmarkError(f"{SOURCE_NAME} is unreachable: {detail}") from exc

        if response.status_code in (401, 403):
            raise BenchmarkError(f"{SOURCE_NAME} refused the API key")
        if response.status_code == 429:
            raise BenchmarkError(f"{SOURCE_NAME}: daily request limit reached, try again tomorrow")
        if response.status_code >= 400:
            raise BenchmarkError(f"{SOURCE_NAME}: HTTP {response.status_code}")
        try:
            rows = response.json().get("data") or []
        except (ValueError, AttributeError) as exc:
            raise BenchmarkError(f"{SOURCE_NAME} sent an unreadable answer") from exc
        return [entry for row in rows if (entry := parse_entry(row)) is not None]


def parse_entry(row: Any) -> BenchmarkEntry | None:
    """Un modèle de la réponse, ou None s'il lui manque l'essentiel.

    Les indices sont rangés dans `evaluations` ; on accepte aussi un format « à plat », au
    cas où l'API changerait : mieux vaut lire un peu moins que tout rejeter.
    """
    if not isinstance(row, dict) or not row.get("id") or not row.get("name"):
        return None
    evaluations = row["evaluations"] if isinstance(row.get("evaluations"), dict) else row
    creator = row.get("model_creator")
    return BenchmarkEntry(
        source_id=str(row["id"]),
        name=str(row["name"]),
        slug=str(row.get("slug") or ""),
        creator=str(creator["name"]) if isinstance(creator, dict) and creator.get("name") else None,
        intelligence=_number(evaluations.get("artificial_analysis_intelligence_index")),
        coding=_number(evaluations.get("artificial_analysis_coding_index")),
        math=_number(evaluations.get("artificial_analysis_math_index")),
        output_speed=_number(row.get("median_output_tokens_per_second")),
    )


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) else None
