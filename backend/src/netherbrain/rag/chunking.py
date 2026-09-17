"""Découper un texte en morceaux (chunks) qui se chevauchent, pour la recherche."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    content: str
    page: int | None = None


def chunk_text(text: str, size: int = 1200, overlap: int = 200) -> list[str]:
    """Découpe en morceaux d'au plus `size` caractères, qui se chevauchent de `overlap`.

    Pourquoi découper ? Un vecteur résume le sens d'un texte : un petit morceau donne un
    vecteur précis, et on n'envoie au modèle que les passages utiles.
    Pourquoi chevaucher ? Pour qu'une idée coupée en deux reste entière dans l'un des
    morceaux. On coupe de préférence à la fin d'un paragraphe, d'une phrase ou d'un mot.
    """
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    text = text.strip()
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            end = _best_break(text, start + size // 2, end)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        # Le morceau suivant repart un peu avant la fin de celui-ci (le chevauchement),
        # tout en avançant toujours d'au moins un caractère.
        start = max(end - overlap, start + 1)
    return chunks


def _best_break(text: str, earliest: int, latest: int) -> int:
    """La meilleure coupure entre earliest et latest : paragraphe, puis ligne, phrase, mot."""
    window = text[earliest:latest]
    for separator in ("\n\n", "\n", ". ", "? ", "! ", " "):
        position = window.rfind(separator)
        if position != -1:
            return earliest + position + len(separator)
    return latest


def chunk_pages(pages: list[tuple[int | None, str]], size: int, overlap: int) -> list[Chunk]:
    """Découpe page par page, pour pouvoir citer la page d'où vient chaque extrait."""
    return [
        Chunk(content, page) for page, text in pages for content in chunk_text(text, size, overlap)
    ]
