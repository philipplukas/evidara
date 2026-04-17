from __future__ import annotations

from acquisition_core.providers import AcquisitionProvider
from acquisition_core.providers import ProviderRegistry as CoreProviderRegistry
from platform_control.domain import ExecutionMode
from platform_control.errors import ProviderConfigurationError
from platform_control.models.source_version import SourceVersion


class ProviderRegistry(CoreProviderRegistry):
    def get(self, provider_name: str):
        try:
            return super().get(provider_name)
        except KeyError as exc:  # pragma: no cover - simple error adaptation
            raise ProviderConfigurationError(
                f"No acquisition provider configured for '{provider_name}'."
            ) from exc

    def resolve_for_version(self, source_version: SourceVersion) -> AcquisitionProvider:
        """Pick the provider for a ``SourceVersion``, honouring its execution mode.

        Versions with ``execution_mode == SHADOW`` are always routed through the
        cassette provider regardless of what ``acquisition_spec.provider`` declares,
        so scheduler + workflow + webhook paths are exercised without touching the
        upstream server.
        """
        if source_version.execution_mode is ExecutionMode.SHADOW:
            return self.get("cassette")
        return self.resolve_for_spec(source_version.acquisition_spec)
