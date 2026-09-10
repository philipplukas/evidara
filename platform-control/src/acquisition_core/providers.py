from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
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
    identity_locator: str | None = None
    """The URI that identifies *the law*, stable across versions (#850).

    Document identity is a **per-provider decision**, not a global URL preference:
    ``fedlex_sparql``'s stable URI is ``source_url`` (the act-level ELI) while
    ``lexfind_api``'s is ``final_url`` (``/tol/{id}/{lang}``) — its ``source_url``
    is the canton's page, whose path embeds the version dates. No single global
    order can be right for both, and the wrong one mints a fresh ``document_id``
    per version, which is the #652 duplicate mechanism.

    Set this to the version-independent URI when the provider knows it. It travels
    into raw artifact metadata and is preferred by
    :func:`acquisition_core.identity.upstream_locator` over any URL heuristic.
    Leave ``None`` when the provider genuinely does not know — the
    ``source_url``-then-``final_url`` fallback then applies, unchanged.
    """

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


class AcquisitionReadiness(StrEnum):
    """Code-owner key of the ADR-0030 two-key lock.

    Replaces the original ``live_ready: bool``, which could not distinguish two
    states with opposite operator remedies — and so told operators "escalate to
    engineering" about providers that were finished (#743):

    - ``SCAFFOLD``: ``start_run`` is a stub (typically ``NotImplementedError``).
      Registered only so blueprint templates referencing it parse. **Remedy:
      engineering.** No run of any mode may dispatch.
    - ``AWAITING_EVIDENCE``: ``start_run`` is implemented and tested, and the
      provider can physically acquire its format — but no operator has captured
      an ADR-0030 acceptance run yet. **Remedy: run the loop.** An
      ``ACCEPTANCE`` run may dispatch against the live portal; nothing else may.
    - ``LIVE``: acceptance evidence exists and was accepted. Runs of any mode
      dispatch once the config key is also open.

    ``AWAITING_EVIDENCE`` exists because the binary deadlocked: acceptance
    evidence requires a live run, a live run required the code key, and the code
    key was supposed to require the evidence. A provider could never earn its own
    first key without a code change, which made every new source an engineering
    project — the exact failure ADR-0033/#628 measure against.
    """

    SCAFFOLD = "scaffold"
    AWAITING_EVIDENCE = "awaiting_evidence"
    LIVE = "live"


class AcquisitionProvider(Protocol):
    provider_name: str
    # The code-owner key. See AcquisitionReadiness for the three states.
    #
    # Whether a template is safe to enable for live acquisition is the *config*
    # key, held separately per blueprint template via `enabled: true` in
    # source_blueprints.yaml (DB override wins). An operator flips that after
    # capturing acceptance-run evidence; this field is engineering's assertion
    # about the code, not the operator's about the corpus.
    readiness: AcquisitionReadiness

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
    """Raised when the code-owner key refuses a dispatch.

    The two-key lock requires `template.enabled: true` AND a provider whose
    readiness admits the run. This exception fires when the second key fails.
    The message names *which* state blocked, because the remedy differs: a
    SCAFFOLD needs engineering, an AWAITING_EVIDENCE provider needs an
    acceptance run the operator can drive themselves (#743).
    """


def provider_readiness(provider: AcquisitionProvider) -> AcquisitionReadiness:
    """Resolve a provider's readiness, failing closed.

    Accepts the legacy ``live_ready: bool`` as an input so third-party and test
    doubles that predate the enum keep working: ``True`` maps to ``LIVE`` and
    ``False`` to ``SCAFFOLD``, which is the binary's original meaning. A provider
    declaring neither resolves to ``SCAFFOLD`` — unknown must never mean
    launchable, the same fail-closed default the bool had.
    """
    declared = getattr(provider, "readiness", None)
    if declared is not None:
        try:
            return AcquisitionReadiness(declared)
        except ValueError:
            # An unrecognised state is not a reason to open the lock.
            return AcquisitionReadiness.SCAFFOLD
    if getattr(provider, "live_ready", False):
        return AcquisitionReadiness.LIVE
    return AcquisitionReadiness.SCAFFOLD


def ensure_launchable(
    provider: AcquisitionProvider,
    *,
    template_id: str | None = None,
    for_acceptance: bool = False,
) -> AcquisitionProvider:
    """Provider-side key of the two-key lock (ADR-0030).

    Shared by ``ProviderRegistry`` and by the run-launch path, which holds an
    already-resolved provider (the SHADOW execution mode swaps in the cassette
    provider, so the run-launch path must gate the provider it will actually
    call, not the one the acquisition spec names).

    ``for_acceptance`` marks an ADR-0030 acceptance run — the operator's
    rehearsal against the live portal that *produces* the evidence for flipping
    the keys. It admits ``AWAITING_EVIDENCE`` and nothing more: a SCAFFOLD still
    cannot dispatch, because there is no implementation to gather evidence about.
    """
    readiness = provider_readiness(provider)
    if readiness is AcquisitionReadiness.LIVE:
        return provider
    if readiness is AcquisitionReadiness.AWAITING_EVIDENCE and for_acceptance:
        return provider

    provider_name = getattr(provider, "provider_name", type(provider).__name__)
    if readiness is AcquisitionReadiness.AWAITING_EVIDENCE:
        raise ProviderNotLiveReadyError(
            f"Provider {provider_name!r} is implemented but has no acceptance-run "
            f"evidence yet (template_id={template_id!r}). Dispatch an acceptance run "
            "to capture it — this does not need an engineer (ADR-0030)."
        )
    raise ProviderNotLiveReadyError(
        f"Provider {provider_name!r} is a scaffold and cannot run "
        f"(template_id={template_id!r}). See the provider's runbook for "
        "live-enablement criteria."
    )


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
        """Return provider names an *enabled* blueprint template may reference.

        Only LIVE qualifies. An AWAITING_EVIDENCE provider performs real work, but
        a template enabled against it would dispatch production runs on evidence
        nobody captured — which is the invariant
        `test_enabled_templates_only_reference_live_ready_providers` guards.
        """
        return {
            name
            for name, provider in self._providers.items()
            if provider_readiness(provider) is AcquisitionReadiness.LIVE
        }

    def resolve_for_spec(self, acquisition_spec: dict[str, Any] | None) -> AcquisitionProvider:
        provider_name = str((acquisition_spec or {}).get("provider") or "firecrawl")
        return self.get(provider_name)

    def require_live_ready(
        self,
        acquisition_spec: dict[str, Any] | None,
        *,
        template_id: str | None = None,
        for_acceptance: bool = False,
    ) -> AcquisitionProvider:
        """Two-key lock for blueprint resolution.

        Raises ProviderNotLiveReadyError when the requested provider's readiness
        does not admit the run. Callers that merely want to resolve-and-introspect
        can keep using resolve_for_spec(); the loader path for launching a run
        should use this method so scaffolds cannot fire at runtime.
        """
        return ensure_launchable(
            self.resolve_for_spec(acquisition_spec),
            template_id=template_id,
            for_acceptance=for_acceptance,
        )
