"""Les images jointes au chat : ce que le modèle en reçoit."""

import base64
import uuid
from collections.abc import Sequence

from netherbrain.db.models import Document
from netherbrain.providers import LLMProvider, ProviderError
from netherbrain.schemas import ChatMessage, ImageInput


async def can_read_images(provider: LLMProvider, model: str) -> bool | None:
    """Le modèle sait-il lire des images ? None si le fournisseur ne peut pas le dire."""
    try:
        cards = await provider.describe_models()
    except ProviderError:
        return None
    card = next((card for card in cards if card.id == model), None)
    return None if card is None else "vision" in card.capabilities


def add_images(
    history: list[ChatMessage],
    senders: list[uuid.UUID | None],
    images: Sequence[Document],
    *,
    limit: int,
    vision: bool,
) -> None:
    """Joint chaque image au message de l'utilisateur qui l'a envoyée.

    `senders` donne, pour chaque message de l'historique, son identifiant en base (None pour
    le message en cours d'envoi). Seules les `limit` images les plus récentes partent : les
    autres, ou toutes si le modèle ne sait pas lire d'images, sont seulement mentionnées,
    pour que le modèle sache qu'elles existent sans prétendre les voir.
    """
    shown = {image.id for image in images[-limit:]} if vision and limit > 0 else set()
    by_sender: dict[uuid.UUID | None, list[Document]] = {}
    for image in images:
        by_sender.setdefault(image.message_id, []).append(image)

    for message, sender in zip(history, senders, strict=True):
        for image in by_sender.get(sender, []):
            if image.id in shown and image.data is not None:
                data = base64.b64encode(image.data).decode("ascii")
                message.images = [
                    *(message.images or []),
                    ImageInput(media_type=image.content_type, data=data),
                ]
            else:
                message.content += f"\n\n[Image {image.name}: not shown to you]"
