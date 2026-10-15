"""Les réponses attendues de l'utilisateur : autoriser une action, ou répondre à une question.

Un stream SSE ne va que du serveur vers le navigateur : la réponse de l'utilisateur arrive
donc par une autre requête HTTP. Les demandes vivent en mémoire, dans ce registre, ce qui
suppose un seul processus d'API (c'est le cas ici). À plusieurs, il faudrait un espace
partagé, Redis par exemple.
"""

import asyncio
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# once : cette fois ; always : pour toute la conversation (l'outil, ou le dossier demandé) ;
# deny : refus ; answer : la réponse à une question de l'agent (ask_user).
Decision = Literal["once", "always", "deny", "answer"]


@dataclass(frozen=True)
class Reply:
    decision: Decision
    answer: str | None = None


class ApprovalRegistry:
    def __init__(self, timeout: float = 300.0) -> None:
        self._timeout = timeout
        self._pending: dict[tuple[uuid.UUID, str], asyncio.Future[Reply]] = {}
        self._always: dict[uuid.UUID, set[str]] = {}
        self._folders: dict[uuid.UUID, set[Path]] = {}

    def allowed(self, conversation_id: uuid.UUID, tool: str) -> bool:
        """L'utilisateur a-t-il déjà autorisé cet outil pour toute la conversation ?"""
        return tool in self._always.get(conversation_id, set())

    def folders(self, conversation_id: uuid.UUID) -> list[Path]:
        """Les dossiers hors du projet que l'utilisateur a ouverts pour toute la conversation."""
        return sorted(self._folders.get(conversation_id, set()))

    def pending_calls(self, conversation_id: uuid.UUID) -> list[str]:
        return [call for (conv, call) in self._pending if conv == conversation_id]

    async def wait(
        self,
        conversation_id: uuid.UUID,
        call_id: str,
        tool: str,
        *,
        folder: Path | None = None,
        once_only: bool = False,
    ) -> Reply | None:
        """Attend la réponse de l'utilisateur ; None s'il ne répond pas à temps.

        « always » ouvre `folder` pour toute la conversation quand l'appel demandait un
        dossier, et sinon autorise l'outil. Avec `once_only` (un fichier de secrets, une
        commande, le dossier personnel entier), il ne vaut que cette fois : l'utilisateur sera
        redemandé.
        """
        key = (conversation_id, call_id)
        future: asyncio.Future[Reply] = asyncio.get_running_loop().create_future()
        self._pending[key] = future
        try:
            async with asyncio.timeout(self._timeout):
                reply = await future
        except TimeoutError:
            return None
        finally:
            self._pending.pop(key, None)

        if reply.decision == "always" and not once_only:
            if folder is not None:
                self._folders.setdefault(conversation_id, set()).add(folder)
            else:
                self._always.setdefault(conversation_id, set()).add(tool)
        return reply

    def answer(self, conversation_id: uuid.UUID, call_id: str, reply: Reply) -> bool:
        """Transmet la réponse au stream qui l'attend ; False si plus personne n'attend."""
        future = self._pending.get((conversation_id, call_id))
        if future is None or future.done():
            return False
        future.set_result(reply)
        return True

    def forget(self, conversation_id: uuid.UUID) -> None:
        self._always.pop(conversation_id, None)
        self._folders.pop(conversation_id, None)
