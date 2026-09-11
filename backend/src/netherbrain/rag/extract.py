"""Extraire le texte d'un fichier importé : PDF, texte brut ou Markdown."""

import io

from pypdf import PdfReader

# Le type est déduit de l'extension : celui qu'annonce le navigateur est peu fiable.
SUPPORTED_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
}


class UnsupportedDocumentError(ValueError):
    """Le fichier n'est pas d'un type pris en charge, ou son contenu est illisible."""


def content_type_for(filename: str) -> str:
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    try:
        return SUPPORTED_TYPES[extension]
    except KeyError:
        raise UnsupportedDocumentError(
            f"Unsupported file type '{extension or 'none'}': use PDF, TXT or Markdown"
        ) from None


def extract_pages(data: bytes, content_type: str) -> list[tuple[int | None, str]]:
    """Le texte du fichier, page par page pour un PDF (pages numérotées à partir de 1)."""
    if content_type == "application/pdf":
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
