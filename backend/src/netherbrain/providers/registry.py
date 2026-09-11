import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from netherbrain.providers.base import LLMProvider, ProviderError
from netherbrain.schemas import ModelCard


class UnknownProviderError(LookupError):
    """Levée quand une requête désigne un fournisseur qui n'est pas configuré."""


@dataclass
class ProviderResult[T]:
    """Ce qu'a répondu un fournisseur, ou pourquoi il n'a pas répondu."""

    name: str
    local: bool = False
    items: list[T] = field(default_factory=list)
    error: str | None = None


class ProviderRegistry:
    """Tous les fournisseurs configurés, accessibles par leur nom."""

    def __init__(self, providers: list[LLMProvider], list_timeout: float = 5.0) -> None:
        self._providers = {provider.name: provider for provider in providers}
        self._list_timeout = list_timeout

    @property
    def names(self) -> list[str]:
        return list(self._providers)

    def get(self, name: str) -> LLMProvider:
        try:
            return self._providers[name]
        except KeyError:
            raise UnknownProviderError(name) from None

    async def list_all(self) -> list[ProviderResult[str]]:
        """Les identifiants des modèles de chaque fournisseur (pour choisir dans le chat)."""
        return await self._ask_all(lambda provider: provider.list_models())

    async def describe_all(self) -> list[ProviderResult[ModelCard]]:
        """Les fiches détaillées des modèles de chaque fournisseur (pour le catalogue)."""
        return await self._ask_all(lambda provider: provider.describe_models())

    async def _ask_all[T](
        self, ask: Callable[[LLMProvider], Awaitable[list[T]]]
    ) -> list[ProviderResult[T]]:
        """Interroge tous les fournisseurs en parallèle.

        Dégradation gracieuse : un fournisseur en panne, lent ou hors ligne est signalé
        comme indisponible, il n'empêche jamais les autres de répondre.
        """
        return await asyncio.gather(
            *(self._ask_one(provider, ask) for provider in self._providers.values())
        )

    async def _ask_one[T](
        self, provider: LLMProvider, ask: Callable[[LLMProvider], Awaitable[list[T]]]
    ) -> ProviderResult[T]:
        outcome: ProviderResult[T] = ProviderResult(provider.name, local=provider.local)
        try:
            async with asyncio.timeout(self._list_timeout):
                outcome.items = await ask(provider)
        except TimeoutError:
            outcome.error = f"no answer after {self._list_timeout:g}s"
        except ProviderError as exc:
            outcome.error = str(exc)
        return outcome
