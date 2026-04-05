from acquisition_core.providers import ProviderRegistry as CoreProviderRegistry
from platform_control.errors import ProviderConfigurationError


class ProviderRegistry(CoreProviderRegistry):
    def get(self, provider_name: str):
        try:
            return super().get(provider_name)
        except KeyError as exc:  # pragma: no cover - simple error adaptation
            raise ProviderConfigurationError(
                f"No acquisition provider configured for '{provider_name}'."
            ) from exc
