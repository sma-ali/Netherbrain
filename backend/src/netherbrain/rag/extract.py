"""Extraire le texte d'un fichier joint : un PDF, ou n'importe quel fichier texte (code compris)."""

import io

from pypdf import PdfReader

PDF = "application/pdf"
MARKDOWN_EXTENSIONS = {".md", ".markdown"}
# Un fichier binaire (image, archive, exécutable) contient presque toujours des octets nuls
# dès ses premiers kilo-octets : pas besoin de tout lire pour le reconnaître.
SNIFF_BYTES = 8000


class UnsupportedDocumentError(ValueError):
    """Le fichier n'est pas d'un type pris en charge, ou son contenu est illisible."""


def content_type_for(filename: str, data: bytes) -> str:
    """Le type du fichier, déduit de son extension et de son contenu.

    Le type annoncé par le navigateur est peu fiable, et souvent vide pour du code. Un PDF se
    reconnaît à son extension ; tout le reste est accepté s'il s'agit de texte UTF-8, quelle
    que soit l'extension (Dockerfile, .py, .tsx, .csv…).
    """
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension == ".pdf":
        return PDF
    if b"\x00" in data[:SNIFF_BYTES]:
        raise UnsupportedDocumentError(
            f"{filename} is not a text file: attach PDFs or text files (code, Markdown, CSV…)"
        )
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        raise UnsupportedDocumentError(f"{filename} is not UTF-8 text") from None
    return "text/markdown" if extension in MARKDOWN_EXTENSIONS else "text/plain"


def extract_pages(data: bytes, content_type: str) -> list[tuple[int | None, str]]:
    """Le texte du fichier, page par page pour un PDF (pages numérotées à partir de 1)."""
    if content_type == PDF:
        try:
            reader = PdfReader(io.BytesIO(data))
            pages = [
                (number, page.extract_text() or "")
                for number, page in enumerate(reader.pages, start=1)
            ]
        except Exception as exc:
            # Un PDF abîmé peut lever toutes sortes d'erreurs dans pypdf : on les regroupe.
            raise UnsupportedDocumentError(f"Unreadable PDF: {exc}") from exc
    else:
        pages = [(None, data.decode("utf-8", errors="replace"))]

    pages = [(page, text) for page, text in pages if text.strip()]
    if not pages:
        raise UnsupportedDocumentError(
            "No text found (a scanned PDF would need OCR, which is not supported yet)"
        )
    return pages


def pages_to_text(pages: list[tuple[int | None, str]]) -> str:
    """Le texte complet, avec des repères de page pour que le modèle puisse les citer."""
    return "\n\n".join(
        f"[page {page}]\n{text.strip()}" if page else text.strip() for page, text in pages
    )
