from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class ProviderResource:
    """A single acquired manifestation carried from a provider to the artifact pipeline.

    A manifestation is either **text** (``body``, e.g. HTML/XML/plain text) or
    **binary** (``body_bytes``, e.g. a PDF). Exactly one of the two is set. Binary
    support (#590) exists because municipal Swiss law is largely PDF-only: the
    operative ordinance has no HTML manifestation, so the acquisition interface must
    be able to carry raw bytes end-to-end, not just decode-able text.

    Downstream code should read :attr:`raw_bytes` (the modality-agnostic payload used
    for hashing and storage) and branch on :attr:`is_binary` when it needs the text.
    """

    source_url: str
    final_url: str
    content_type: str
    body: str | None = None
    body_bytes: bytes | None = None
    title: str | None = None
    http_status: int | None = None
    discovery_depth: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.body is not None and self.body_bytes is not None:
            raise ValueError(
                "ProviderResource carries exactly one manifestation: set body (text) "
                "or body_bytes (binary), not both."
            )
        if self.body is None and self.body_bytes is None:
            raise ValueError(
                "ProviderResource requires a manifestation: set body (text) or body_bytes (binary)."
            )

    @property
    def is_binary(self) -> bool:
        """True when this resource carries a binary (non-text) manifestation."""
        return self.body_bytes is not None

    @property
    def raw_bytes(self) -> bytes:
        """Modality-agnostic payload bytes — for checksums and durable storage.

        For a text manifestation this is the UTF-8 encoding of ``body``; for a binary
        manifestation it is ``body_bytes`` verbatim.
        """
        if self.body_bytes is not None:
            return self.body_bytes
        assert self.body is not None  # guaranteed by __post_init__
        return self.body.encode("utf-8")


@dataclass(slots=True)
class ProviderStartResult:
    external_job_id: str
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
    provider: str = "firecrawl"
    inline_resources: list[ProviderResource] = field(default_factory=list)
    inline_failure_reason: str | None = None


@dataclass(slots=True)
class ProviderPlan:
    """Static description of what ``start_run`` would execute, without touching the network.

    Enables ``pc source plan`` and shadow-mode dispatch to surface budget, targets
    and policy without spending an external API call.
    """

    provider: str
    mode: str | None = None
    seed_urls: list[str] = field(default_factory=list)
    estimated_request_count: int | None = None
    max_discovery_depth: int | None = None
    include_paths: list[str] = field(default_factory=list)
    exclude_paths: list[str] = field(default_factory=list)
    user_agent: str | None = None
    request_timeout_seconds: float | None = None
    notes: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


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

    def plan(
        self,
        source: Any,
        source_version: Any,
    ) -> ProviderPlan:
        """Return the acquisition plan ``start_run`` would execute, without network IO."""
        ...


class ProviderNotLiveReadyError(RuntimeError):
    """Raised when a blueprint template references a provider that is a scaffold.

    The two-key lock requires `template.enabled: true` AND
    `provider.live_ready: true`; this exception fires when the second key
    fails. Message points at the relevant scaffold runbook so an operator
    knows which follow-up ticket owns live-enablement.
    """


def ensure_live_ready(
    provider: AcquisitionProvider,
    *,
    template_id: str | None = None,
) -> AcquisitionProvider:
    """Provider-side key of the two-key lock (ADR-0030).

    Raises ProviderNotLiveReadyError when ``provider`` is a scaffold
    (``live_ready`` falsy or absent). Shared by ``ProviderRegistry`` and by
    the run-launch path, which holds an already-resolved provider (the
    SHADOW execution mode swaps in the cassette provider, so the run-launch
    path must gate the provider it will actually call, not the one the
    acquisition spec names).
    """
    if not getattr(provider, "live_ready", False):
        provider_name = getattr(provider, "provider_name", type(provider).__name__)
        raise ProviderNotLiveReadyError(
            f"Provider {provider_name!r} is a scaffold and cannot run "
            f"(template_id={template_id!r}). See the provider's runbook for "
            "live-enablement criteria."
        )
    return provider


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
            name
            for name, provider in self._providers.items()
            if getattr(provider, "live_ready", False)
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

        Raises ProviderNotLiveReadyError when the requested provider is a
        scaffold. Callers that merely want to resolve-and-introspect can
        keep using resolve_for_spec(); the loader path for launching a run
        should use this method so scaffolds cannot fire at runtime.
        """
        return ensure_live_ready(
            self.resolve_for_spec(acquisition_spec),
            template_id=template_id,
        )
