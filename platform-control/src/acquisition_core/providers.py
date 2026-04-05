from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class ProviderResource:
    source_url: str
    final_url: str
    content_type: str
    body: str
    title: str | None = None
    http_status: int | None = None
    discovery_depth: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderStartResult:
    external_job_id: str
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
    provider: str = "firecrawl"
    inline_resources: list[ProviderResource] = field(default_factory=list)
    inline_failure_reason: str | None = None


class AcquisitionProvider(Protocol):
    provider_name: str

    async def start_run(
        self,
        source: Any,
        source_version: Any,
        run: Any,
    ) -> ProviderStartResult: ...


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, AcquisitionProvider] = {}

    def register(self, provider: AcquisitionProvider) -> None:
        self._providers[provider.provider_name] = provider

    def get(self, provider_name: str) -> AcquisitionProvider:
        provider = self._providers.get(provider_name)
        if provider is None:
            raise KeyError(provider_name)
        return provider

    def resolve_for_spec(self, acquisition_spec: dict[str, Any] | None) -> AcquisitionProvider:
        provider_name = str((acquisition_spec or {}).get("provider") or "firecrawl")
        return self.get(provider_name)
