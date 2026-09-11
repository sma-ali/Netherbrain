import asyncio
from dataclasses import dataclass, field

from netherbrain.providers.base import LLMProvider, ProviderError


class UnknownProviderError(LookupError):
    """Levée quand une requête désigne un fournisseur qui n'est pas configuré."""


@dataclass
class ProviderModels:
    """Le résultat de la demande de modèles à un fournisseur."""

    name: str
    models: list[str] = field(default_factory=list)
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

    async def list_all(self) -> list[ProviderModels]:
        """Interroge tous les fournisseurs en parallèle.

        Dégradation gracieuse : un fournisseur en panne, lent ou hors ligne est signalé
        comme indisponible, il n'empêche jamais les autres d'être listés.
        """
        return await asyncio.gather(*(self._list_one(p) for p in self._providers.values()))

    async def _list_one(self, provider: LLMProvider) -> ProviderModels:
        try:
            async with asyncio.timeout(self._list_timeout):
                models = await provider.list_models()
        except TimeoutError:
            return ProviderModels(provider.name, error=f"no answer after {self._list_timeout:g}s")
        except ProviderError as exc:
            return ProviderModels(provider.name, error=str(exc))
        return ProviderModels(provider.name, models=models)
