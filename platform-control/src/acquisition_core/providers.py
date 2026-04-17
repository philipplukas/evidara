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
    # live_ready distinguishes scaffolds from implementations:
    # - True: the provider's `start_run` is internally consistent and
    #   mocked tests cover the logic against its target API contract.
    #   Blueprint templates MAY reference it and, once the operator
    #   enables a template, runs go live.
    # - False: `start_run` is a stub (typically raises NotImplementedError).
    #   The provider is registered only so blueprint templates referencing
    #   it parse, but the loader's two-key lock rejects any run attempt.
    #
    # Production-readiness (whether a template is safe to enable for live
    # acquisition) lives separately on each blueprint template via
    # `enabled: true` in source_blueprints.yaml. An operator flips that
    # after capturing acceptance-run evidence.
    live_ready: bool

    async def start_run(
        self,
        source: Any,
        source_version: Any,
        run: Any,
    ) -> ProviderStartResult: ...


class ProviderNotLiveReady(RuntimeError):
    """Raised when a blueprint template references a provider that is a scaffold.

    The two-key lock requires `template.enabled: true` AND
    `provider.live_ready: true`; this exception fires when the second key
    fails. Message points at the relevant scaffold runbook so an operator
    knows which follow-up ticket owns live-enablement.
    """


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

    def live_ready_names(self) -> set[str]:
        """Return provider names whose start_run() performs real work."""
        return {
            name for name, provider in self._providers.items() if getattr(provider, "live_ready", False)
        }

    def resolve_for_spec(self, acquisition_spec: dict[str, Any] | None) -> AcquisitionProvider:
        provider_name = str((acquisition_spec or {}).get("provider") or "firecrawl")
        return self.get(provider_name)

    def require_live_ready(
        self,
        acquisition_spec: dict[str, Any] | None,
        *,
        template_id: str | None = None,
    ) -> AcquisitionProvider:
        """Two-key lock for blueprint resolution.

        Raises ProviderNotLiveReady when the requested provider is a
        scaffold. Callers that merely want to resolve-and-introspect can
        keep using resolve_for_spec(); the loader path for launching a run
        should use this method so scaffolds cannot fire at runtime.
        """
        provider = self.resolve_for_spec(acquisition_spec)
        if not getattr(provider, "live_ready", False):
            raise ProviderNotLiveReady(
                f"Provider {provider.provider_name!r} is a scaffold and cannot run "
                f"(template_id={template_id!r}). See the provider's runbook for "
                "live-enablement criteria."
            )
        return provider
