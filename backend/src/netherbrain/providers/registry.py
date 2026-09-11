import asyncio
from dataclasses import dataclass, field

from netherbrain.providers.base import LLMProvider, ProviderError


class UnknownProviderError(LookupError):
    """Raised when a request names a provider that is not configured."""


@dataclass
class ProviderModels:
    """The outcome of asking one provider for its models."""

    name: str
    models: list[str] = field(default_factory=list)
    error: str | None = None


class ProviderRegistry:
    """Every configured provider, addressable by name."""

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
        """Ask every provider concurrently.

        Graceful degradation: a provider that is down, slow or offline is reported
        as unavailable, it never prevents the others from being listed.
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
