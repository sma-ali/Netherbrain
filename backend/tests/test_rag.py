"""Les briques du RAG, testées une par une : découpage, extraction, embeddings."""

import asyncio
import json
from itertools import pairwise

import httpx
import pytest

from netherbrain.rag.chunking import Chunk, chunk_pages, chunk_text
from netherbrain.rag.embeddings import EmbeddingError, OllamaEmbedder, cosine_similarity
from netherbrain.rag.extract import (
    UnsupportedDocumentError,
    content_type_for,
    extract_pages,
    pages_to_text,
)


def make_pdf(pages: list[str]) -> bytes:
    """Un PDF minimal écrit à la main : une ligne de texte (ASCII) par page."""
    font_id = 3 + 2 * len(pages)
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>",
    ]
    for i, line in enumerate(pages):
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {4 + 2 * i} 0 R >>"
        )
        stream = f"BT /F1 12 Tf 72 720 Td ({line}) Tj ET"
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    pdf = "%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{number} 0 obj\n{body}\nendobj\n"
    xref = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    pdf += "".join(f"{offset:010d} 00000 n \n" for offset in offsets)
    pdf += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    return pdf.encode("latin-1")


# --- Découpage ---

SENTENCES = " ".join(f"Voici la phrase numéro {i}." for i in range(200))


def test_a_short_text_is_a_single_chunk():
    assert chunk_text("Bonjour.", size=100, overlap=20) == ["Bonjour."]


def test_an_empty_text_gives_no_chunk():
    assert chunk_text("   ", size=100, overlap=20) == []


def test_chunks_respect_the_size_and_overlap():
    chunks = chunk_text(SENTENCES, size=300, overlap=50)

    assert len(chunks) > 10
    assert all(len(chunk) <= 300 for chunk in chunks)
    # Chaque morceau commence par un passage qui termine le précédent (le chevauchement).
    assert all(following[:10] in previous for previous, following in pairwise(chunks))


def test_chunks_end_at_the_end_of_a_sentence():
    chunks = chunk_text(SENTENCES, size=300, overlap=50)

    assert all(chunk.endswith(".") for chunk in chunks)


def test_the_overlap_must_be_smaller_than_the_size():
    with pytest.raises(ValueError):
        chunk_text(SENTENCES, size=100, overlap=100)


def test_pages_are_kept_for_citations():
    assert chunk_pages([(1, "Page un."), (2, "Page deux.")], size=100, overlap=10) == [
        Chunk("Page un.", 1),
        Chunk("Page deux.", 2),
    ]


# --- Extraction ---


def test_text_files_are_read_as_utf8():
    assert extract_pages("Héllo".encode(), "text/plain") == [(None, "Héllo")]


def test_pdf_text_is_extracted_page_by_page():
    pages = extract_pages(make_pdf(["Hello page one", "", "Third page"]), "application/pdf")

    # La page vide disparaît, les autres gardent leur numéro.
    assert [(number, text.strip()) for number, text in pages] == [
        (1, "Hello page one"),
        (3, "Third page"),
    ]


@pytest.mark.parametrize("data", [b"%PDF-1.4 not really a pdf", make_pdf([""])])
def test_unreadable_or_empty_pdfs_are_refused(data):
    with pytest.raises(UnsupportedDocumentError):
        extract_pages(data, "application/pdf")


@pytest.mark.parametrize(
    ("filename", "data", "expected"),
    [
        ("rapport.PDF", b"%PDF-1.4", "application/pdf"),
        ("notes.md", b"# Titre", "text/markdown"),
        ("Dockerfile", b"FROM python:3.14", "text/plain"),
        ("App.tsx", "const titre = 'Été'".encode(), "text/plain"),
    ],
)
def test_pdfs_and_any_text_file_are_accepted(filename, data, expected):
    assert content_type_for(filename, data) == expected


@pytest.mark.parametrize(
    ("filename", "data"),
    [
        ("photo.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"),
        ("ancien.txt", "Été".encode("latin-1")),
    ],
)
def test_binary_or_non_utf8_files_are_refused(filename, data):
    with pytest.raises(UnsupportedDocumentError):
        content_type_for(filename, data)


def test_pages_are_marked_so_the_model_can_cite_them():
    assert pages_to_text([(1, "Un. "), (3, "Trois.")]) == "[page 1]\nUn.\n\n[page 3]\nTrois."
    assert pages_to_text([(None, "  texte  ")]) == "texte"


# --- Embeddings ---


def test_cosine_similarity():
    assert cosine_similarity([1, 0], [2, 0]) == 1
    assert cosine_similarity([1, 0], [0, 3]) == 0
    assert cosine_similarity([0, 0], [1, 1]) == 0


def test_ollama_embeddings_are_batched_and_prefixed():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2] for _ in body["input"]]})

    embedder = OllamaEmbedder(
        "http://ollama.test:11434/v1",
        "nomic-embed-text",
        document_prefix="doc: ",
        query_prefix="query: ",
        batch_size=2,
        transport=httpx.MockTransport(handler),
    )

    vectors = asyncio.run(embedder.embed_documents(["a", "b", "c"]))
    asyncio.run(embedder.embed_query("q"))

    assert len(vectors) == 3
    assert [r["input"] for r in requests] == [["doc: a", "doc: b"], ["doc: c"], ["query: q"]]
    assert requests[0]["model"] == "nomic-embed-text"


def test_a_missing_embedding_model_gives_the_command_to_install_it():
    transport = httpx.MockTransport(lambda _: httpx.Response(404, json={"error": "not found"}))
    embedder = OllamaEmbedder(
        "http://ollama.test:11434/v1", "nomic-embed-text", transport=transport
    )

    with pytest.raises(EmbeddingError, match="ollama pull nomic-embed-text"):
        asyncio.run(embedder.embed_query("q"))


def test_a_model_with_the_wrong_vector_size_is_refused():
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"embeddings": [[0.1] * 3]}))
    embedder = OllamaEmbedder("http://ollama.test", "tiny", dimensions=768, transport=transport)

    with pytest.raises(EmbeddingError, match="768"):
        asyncio.run(embedder.embed_query("q"))
