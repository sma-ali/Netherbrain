"""Transformer des textes en vecteurs (embeddings) avec un modèle servi par Ollama."""

import math
from collections.abc import Sequence
from typing import Protocol

import httpx


class EmbeddingError(Exception):
    """Le modèle d'embeddings est injoignable, absent, ou incompatible."""


class Embedder(Protocol):
    """Ce que le RAG attend d'un modèle d'embeddings."""

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class OllamaEmbedder:
    """Embeddings calculés en local par Ollama, via son API native (POST /api/embed)."""

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        document_prefix: str = "",
        query_prefix: str = "",
        dimensions: int | None = None,
        batch_size: int = 32,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        # http://localhost:11434/v1 → http://localhost:11434/api/embed
        self._url = base_url.rstrip("/").removesuffix("/v1") + "/api/embed"
        self._document_prefix = document_prefix
        self._query_prefix = query_prefix
        self._dimensions = dimensions
        self._batch_size = batch_size
        # Les tests remplacent le réseau par une réponse préparée à l'avance.
        self._transport = transport

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        # Certains modèles (dont nomic-embed-text) veulent savoir si le texte est un
        # document ou une question : c'est le rôle des préfixes.
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            vectors.extend(await self._embed([self._document_prefix + text for text in batch]))
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([self._query_prefix + text]))[0]

    async def _embed(self, inputs: list[str]) -> list[list[float]]:
        try:
            async with httpx.AsyncClient(timeout=120, transport=self._transport) as client:
                response = await client.post(self._url, json={"model": self.model, "input": inputs})
        except httpx.HTTPError as exc:
            raise EmbeddingError(
                f"embedding model unreachable ({str(exc) or type(exc).__name__})"
            ) from exc
        if response.status_code == 404:
            raise EmbeddingError(
                f"embedding model '{self.model}' not found: run `ollama pull {self.model}`"
            )
        if response.is_error:
            raise EmbeddingError(f"embedding failed (HTTP {response.status_code})")

        vectors = response.json()["embeddings"]
        if self._dimensions and any(len(vector) != self._dimensions for vector in vectors):
            raise EmbeddingError(
                f"'{self.model}' returns {len(vectors[0])}-dimension vectors, the database "
                f"expects {self._dimensions}"
            )
        return vectors


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Proximité de sens entre deux vecteurs : 1 = même direction, 0 = sans rapport."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norms = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norms if norms else 0.0
