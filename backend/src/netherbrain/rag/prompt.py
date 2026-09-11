"""Transformer les extraits retrouvés en consigne pour le modèle."""

from netherbrain.schemas import Source

# La consigne reste en anglais : c'est la langue que les modèles suivent le plus fidèlement.
INSTRUCTIONS = (
    "Answer using the excerpts from the user's documents below when they are relevant. "
    "Cite them with their number in square brackets, like [1]. If the excerpts do not "
    "contain the answer, say so, then answer from your own knowledge if you can. "
    "Always answer in the language of the user's question."
)


def describe(source: Source) -> str:
    return f"{source.document_name}, page {source.page}" if source.page else source.document_name


def build_context(sources: list[Source]) -> str:
    """Le message système qui donne au modèle les extraits, numérotés pour être cités."""
    excerpts = "\n\n".join(
        f"[{number}] ({describe(source)})\n{source.content}"
        for number, source in enumerate(sources, start=1)
    )
    return f"{INSTRUCTIONS}\n\n{excerpts}"
