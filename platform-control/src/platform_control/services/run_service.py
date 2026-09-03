from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from acquisition_core.normalization import ArtifactPipeline
from acquisition_core.providers import (
    AcquisitionReadiness,
    ProviderNotLiveReadyError,
    ensure_launchable,
    provider_readiness,
)
from platform_control.config import get_settings
from platform_control.domain import (
    CoverageAttributionStatus,
    ExecutionMode,
    ProviderJobStatus,
    RunMode,
    RunStatus,
    SourceVersionStatus,
)
from platform_control.errors import (
    BlueprintTemplateNotEnabledError,
    DispatchPublishError,
    InvalidStateTransitionError,
    NotFoundError,
    ProviderConfigurationError,
)
from platform_control.events.artifact_bundle import (
    build_artifact_bundle_available_event,
    build_artifact_bundle_manifest,
    build_bundle_extraction_hints,
)
from platform_control.events.publisher import RawArtifactPublisher
from platform_control.ids import generate_prefixed_id
from platform_control.integrations import get_artifact_store, get_raw_artifact_publisher
from platform_control.models.authority import Authority
from platform_control.models.captured_resource import CapturedResource
from platform_control.models.coverage_reconciliation import CoverageReconciliation
from platform_control.models.document_lifecycle_event import DocumentLifecycleEvent
from platform_control.models.processing_status_update import ProcessingStatusUpdate
from platform_control.models.provider_job import ProviderJob
from platform_control.models.raw_artifact import RawArtifact
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.observability import metrics
from platform_control.schemas.run import (
    CapturedResourceListResponse,
    CapturedResourceResponse,
    CreateRunRequest,
    ProviderJobListResponse,
    ProviderJobResponse,
    RawArtifactListResponse,
    RawArtifactResponse,
    RunListItemResponse,
    RunPipelineHealthResponse,
    RunPipelineHealthStage,
    RunPreviewSummaryBreakdownEntry,
    RunPreviewSummaryDriftCheck,
    RunPreviewSummaryResponse,
    RunPreviewSummarySample,
    RunReadinessCheck,
    RunReadinessResponse,
)
from platform_control.services.acquisition_provider import AcquisitionProvider, ProviderResource
from platform_control.services.artifact_store import ArtifactStore
from platform_control.services.blueprint_enablement import BlueprintEnablementService
from platform_control.services.compliance_policy_service import (
    RateLimiterRegistry,
    resolve_rate_limiter_for_source,
    resolve_robots_context_for_source,
)
from platform_control.services.coverage_reconciliation import parse_coverage_payload
from platform_control.services.politeness import current_rate_limiter
from platform_control.services.provider_registry import ProviderRegistry
from platform_control.services.provider_registry_factory import build_provider_registry
from platform_control.services.replay_checkpoint import checkpoint_dict_from_parent
from platform_control.services.robots import RobotsChecker, current_robots_context


@dataclass(slots=True)
class PendingDispatchPublications:
    raw_artifact_ids: list[str] = field(default_factory=list)
    bundle_events: list[dict[str, Any]] = field(default_factory=list)
    # Which run these events hand off. Publication happens *after* the run row is
    # committed, so without this the publisher cannot attribute a failure back to
    # the run it silently broke — which is how #707 left `status: completed`.
    run_id: str | None = None


# Providers whose discovery is a QUERY rather than a URL, mapped to the spec field
# that actually carries it. Used by the `acquisition_seed_present` readiness check
# so an API-driven source is not refused for lacking seeds it does not take.
#
# `lexfind_api` has no list-everything call at all: its API rejects an empty
# search with 400, so `search_text` is the entire discovery surface (#731).
_QUERY_DISCOVERY_KEY_BY_PROVIDER: dict[str, str] = {
    "lexfind_api": "search_text",
}


class RunService:
    _ASYNC_PROVIDER_NAMES = frozenset({"ris_ogd"})
    _DECISION_PATTERN = re.compile(
        r"\b(decision|judg(?:e)?ment|order|case|ruling)\b",
        re.IGNORECASE,
    )
    _BOILERPLATE_PATTERN = re.compile(
        r"\b(privacy|terms|impressum|contact|about|help|faq|cookie|sitemap)\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        session: AsyncSession,
        provider: AcquisitionProvider | None = None,
        provider_registry: ProviderRegistry | None = None,
        artifact_store: ArtifactStore | None = None,
        publisher: RawArtifactPublisher | None = None,
        *,
        run_dispatch_backend: str = "inline",
        rate_limiter_registry: RateLimiterRegistry | None = None,
        robots_checker: RobotsChecker | None = None,
    ) -> None:
        self.session = session
        self.provider = provider
        self.provider_registry = provider_registry
        self.artifact_store = artifact_store or get_artifact_store()
        self.publisher = publisher or get_raw_artifact_publisher()
        self.run_dispatch_backend = run_dispatch_backend
        self.rate_limiter_registry = rate_limiter_registry or RateLimiterRegistry()
        self.robots_checker = robots_checker or RobotsChecker()

    def _resolve_provider_for_source_version(
        self, source_version: SourceVersion
    ) -> AcquisitionProvider | None:
        provider = self.provider
        if provider is None and self.provider_registry is not None:
            provider = self.provider_registry.resolve_for_version(source_version)
        return provider

    async def _require_launchable(
        self,
        source_version: SourceVersion,
        provider: AcquisitionProvider,
        run_mode: RunMode | None = None,
    ) -> None:
        """Two-key lock for the run-launch path (ADR-0030).

        A run may only fire at a third-party portal when BOTH keys are turned:

        - config owner: the blueprint template the version came from is enabled —
          the effective key resolved by `BlueprintEnablementService` (DB override
          an operator flipped, else the shipped `source_blueprints.yaml` default),
          and
        - code owner: the provider that will actually be called is
          ``AcquisitionReadiness.LIVE`` (i.e. `start_run` is not a stub, and
          acceptance evidence has been accepted).

        SHADOW versions are exempt: they are routed to the cassette provider
        and replay fixtures, so no request ever reaches the portal the lock
        protects — a rehearsal that proves nothing about the live portal, which
        is why it cannot serve as acceptance evidence.

        ``RunMode.ACCEPTANCE`` is the other exemption, and the narrow one. It
        reaches the real portal, so it is *not* exempt from the code key — it
        merely admits ``AWAITING_EVIDENCE`` alongside ``LIVE``.

        The config-key waiver turns on *how the key came to be shut*, not on the
        provider's readiness (#768). Two shut keys mean opposite things:

        - **Never turned** (`source="default"`, shipped `enabled: false`). The
          template has never earned evidence. This is the deadlock: acceptance is
          the only sanctioned way to earn the key, so refusing it here makes the
          refusal's own instruction — "capture acceptance-run evidence, then
          enable it" — impossible to follow. Waived.
        - **Explicitly closed** (`source="override"`, `enabled=False`). An
          operator turned it off. This is the kill switch you reach for when an
          authority complains about load, and it is the only audited way to stop
          traffic at one portal without a deploy. Never waived — a waiver here
          would make that switch advisory, which is the load-bearing limit the
          pre-#768 code was protecting.

        Keying on readiness conflated "new provider" with "new template". It
        worked while every provider was new, and silently had no path for a new
        template on a provider already promoted to ``LIVE`` — which is the common
        case as coverage extends along an axis (#584, #731, #736), and is how
        ADR-0033's dog axis stalled.

        The code key is unchanged: ``SCAFFOLD`` still refuses, so a waived config
        key never lets a provider that cannot acquire reach a portal.

        The template must still *exist* in either case. A version pointing at a
        template deleted from `source_blueprints.yaml` — the deploy-time way we
        stop crawling a portal — is refused for acceptance runs too.
        """
        if source_version.execution_mode is ExecutionMode.SHADOW:
            return
        for_acceptance = run_mode is RunMode.ACCEPTANCE
        waive_config_key = for_acceptance
        if waive_config_key and source_version.overlay_id and source_version.provider_template_id:
            state = await BlueprintEnablementService(self.session).get_state(
                source_version.overlay_id, source_version.provider_template_id
            )
            # An operator's explicit close is absolute; only a never-turned key
            # is waived.
            waive_config_key = state.source != "override"
        if source_version.overlay_id and source_version.provider_template_id:
            enablement = BlueprintEnablementService(self.session)
            if waive_config_key:
                # Raises NotFoundError for a template that no longer exists; the
                # returned value is deliberately ignored, since the waiver is
                # about the `enabled` flag alone.
                await enablement.is_enabled(
                    source_version.overlay_id,
                    source_version.provider_template_id,
                )
            else:
                await enablement.require_enabled(
                    source_version.overlay_id,
                    source_version.provider_template_id,
                )
        ensure_launchable(
            provider,
            template_id=source_version.provider_template_id,
            for_acceptance=for_acceptance,
        )

    async def _record_refused_run(
        self,
        source: Source,
        source_version: SourceVersion,
        request: CreateRunRequest,
        reason: str,
    ) -> None:
        """Persist a terminal FAILED run when the two-key lock refuses a dispatch.

        For a platform whose thesis is evidence-gated coverage, a refusal that
        leaves no trace is a hole: an operator cannot later ask what was attempted
        and why it was blocked (#634). This records that attempt as an auditable
        run — status FAILED (terminal, so no worker picks it up), with the lock's
        reason and a `refused` marker in the metadata — then the caller re-raises
        so the API still returns the 400.
        """
        run = Run(
            source_id=source.source_id,
            source_version_id=source_version.source_version_id,
            mode=request.mode,
            status=RunStatus.FAILED,
            failure_reason=reason,
            completed_at=datetime.now(UTC),
            run_metadata={
                "scope": request.scope.model_dump(mode="json"),
                "refused": True,
            },
        )
        self.session.add(run)
        await self.session.commit()

    def _should_dispatch_via_worker(self, source_version: SourceVersion) -> bool:
        if self.run_dispatch_backend == "worker":
            return True
        provider = self._resolve_provider_for_source_version(source_version)
        provider_name = getattr(provider, "provider_name", None)
        return isinstance(provider_name, str) and provider_name in self._ASYNC_PROVIDER_NAMES

    async def list_runs(
        self,
        *,
        mode: RunMode | None = None,
        status: RunStatus | None = None,
        source_id: str | None = None,
        refused: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[RunListItemResponse], int]:
        base_query = (
            select(
                Run.run_id,
                Run.source_id,
                Run.source_version_id,
                Run.mode,
                Run.status,
                Run.started_at,
                Run.completed_at,
                Run.artifacts_count,
                Run.captured_resources_count,
                Run.failure_reason,
                Run.run_metadata.label("run_metadata"),
                Run.created_at,
                Run.updated_at,
                Source.name.label("source_name"),
                SourceVersion.version_label.label("version_label"),
            )
            .join(Source, Source.source_id == Run.source_id)
            .join(SourceVersion, SourceVersion.source_version_id == Run.source_version_id)
            .order_by(Run.created_at.desc())
        )
        if mode is not None:
            base_query = base_query.where(Run.mode == mode)
        if status is not None:
            base_query = base_query.where(Run.status == status)
        if source_id is not None:
            base_query = base_query.where(Run.source_id == source_id)
        if refused is not None:
            # The marker is only written on refusals, so "not refused" must also
            # match rows where the key is absent (every run predating #634).
            is_refused = Run.run_metadata["refused"].as_boolean()
            base_query = base_query.where(
                is_refused.is_(True)
                if refused
                else or_(is_refused.is_(None), is_refused.is_(False))
            )

        count_result = await self.session.execute(
            select(func.count()).select_from(base_query.subquery())
        )
        total = count_result.scalar() or 0

        rows = await self.session.execute(base_query.limit(limit).offset(offset))
        data = [
            RunListItemResponse.model_validate(
                {
                    **{k: v for k, v in row._mapping.items() if k != "run_metadata"},
                    "refused": (row._mapping["run_metadata"] or {}).get("refused") is True,
                }
            )
            for row in rows
        ]
        return data, total

    async def create_run(self, request: CreateRunRequest) -> Run:
        source = await self.session.get(Source, request.source_id)
        if source is None:
            raise NotFoundError(f"Source not found: {request.source_id}")
        source_version = await self.session.get(SourceVersion, request.source_version_id)
        if source_version is None:
            raise NotFoundError(f"Source version not found: {request.source_version_id}")

        readiness = self.assess_run_readiness(
            source=source,
            source_version=source_version,
            source_id=request.source_id,
            source_version_id=request.source_version_id,
            mode=request.mode,
        )
        if not readiness.ready:
            details = "; ".join(check.detail for check in readiness.checks if not check.ok)
            raise InvalidStateTransitionError(f"Run preflight failed: {details}")

        # Two-key lock, checked before a launchable Run row exists: worker-backed
        # dispatch would otherwise accept a run here and only reject it out-of-band,
        # leaving a PENDING run the worker can never dispatch. _dispatch_run
        # re-checks, so scheduler/retry/temporal paths are covered too.
        #
        # A refusal is recorded as a terminal FAILED run before the 400 propagates,
        # so "what did we try to onboard and why did it refuse?" is answerable
        # (#634). It is terminal, not PENDING, so no worker ever picks it up.
        provider = self._resolve_provider_for_source_version(source_version)
        if provider is not None:
            try:
                await self._require_launchable(source_version, provider, request.mode)
            except (BlueprintTemplateNotEnabledError, ProviderNotLiveReadyError) as exc:
                await self._record_refused_run(source, source_version, request, str(exc))
                raise

        run_metadata: dict[str, Any] = {
            "scope": request.scope.model_dump(mode="json"),
            "replay": request.replay.model_dump(mode="json") if request.replay else None,
        }
        if request.replay and request.replay.parent_run_id:
            parent = await self.session.get(Run, request.replay.parent_run_id)
            seeded = checkpoint_dict_from_parent(parent)
            if seeded is not None:
                run_metadata["replay_checkpoint"] = seeded

        run = Run(
            source_id=source.source_id,
            source_version_id=source_version.source_version_id,
            mode=request.mode,
            status=RunStatus.PENDING,
            run_metadata=run_metadata,
        )
        self.session.add(run)
        await self.session.flush()

        if self._should_dispatch_via_worker(source_version):
            await self.session.commit()
            await self.session.refresh(run)
            return run

        pending_publications = await self._dispatch_run(source, source_version, run)
        await self.session.commit()
        await self.session.refresh(run)
        publish_failures = await self._publish_pending_dispatch_events([pending_publications])
        if publish_failures:
            # The run has already been rewritten to FAILED with a reason. Raising
            # turns the bare 500 of #707 into a 502 that names the cause, so the
            # caller learns the handoff died instead of reading `completed` back.
            await self.session.refresh(run)
            raise DispatchPublishError(run.failure_reason or "; ".join(publish_failures))
        return run

    async def get_run_readiness(
        self, *, source_id: str, source_version_id: str, mode: RunMode
    ) -> RunReadinessResponse:
        source = await self.session.get(Source, source_id)
        source_version = await self.session.get(SourceVersion, source_version_id)
        readiness = self.assess_run_readiness(
            source=source,
            source_version=source_version,
            source_id=source_id,
            source_version_id=source_version_id,
            mode=mode,
        )
        # Readiness is the operator's pre-flight ("can I run this?"). It must
        # evaluate the two-key lock too, or it reports `ready: true` for a run
        # that create_run then 400s on the ADR-0030 lock (#634).
        lock_check = await self._assess_launch_lock(source_version, mode)
        if lock_check is None:
            return readiness
        checks = [*readiness.checks, lock_check]
        return RunReadinessResponse(
            source_id=source_id,
            source_version_id=source_version_id,
            mode=mode,
            ready=all(check.ok for check in checks),
            checks=checks,
        )

    async def _assess_launch_lock(
        self, source_version: SourceVersion | None, run_mode: RunMode | None = None
    ) -> RunReadinessCheck | None:
        """Evaluate the ADR-0030 two-key lock as a readiness check.

        Returns None when there is no version to assess (earlier checks already
        fail). Mirrors `_require_launchable` exactly so pre-flight and dispatch
        never disagree: SHADOW is exempt, ACCEPTANCE admits AWAITING_EVIDENCE
        alongside LIVE and waives a config key that was never turned but never
        one an operator explicitly closed (#768), the config key is the effective
        enablement (DB override ?? shipped default), and the code key is the
        resolved provider's readiness. Any divergence between the two here is a
        `ready: true` that create_run then 400s on (#634) — keep them edited
        together.
        """
        if source_version is None:
            return None
        if source_version.execution_mode is ExecutionMode.SHADOW:
            return RunReadinessCheck(
                code="acquisition_lock_open",
                ok=True,
                detail="Shadow mode replays fixtures; the live-portal lock does not apply.",
            )

        # Resolve the provider BEFORE the config key: whether the config key may
        # be waived depends on the provider's readiness, so the order here has to
        # match `_require_launchable`.
        for_acceptance = run_mode is RunMode.ACCEPTANCE
        # An unregistered provider name raises: `ProviderRegistry.get` adapts the
        # core registry's KeyError into ProviderConfigurationError, and the bare
        # core registry still raises KeyError — catch both, since either reaches
        # here depending on which registry was injected. Readiness is a read-only
        # pre-flight and must report this as a closed key rather than 500.
        # Moving resolution ahead of the config-key check made it reachable for a
        # version whose spec names an unknown provider, where the config-key
        # branch used to answer first.
        provider = None
        try:
            provider = self._resolve_provider_for_source_version(source_version)
            if provider is None and self.provider_registry is None:
                provider = build_provider_registry(get_settings()).resolve_for_version(
                    source_version
                )
        except (ProviderConfigurationError, KeyError):
            provider = None

        # A provider we cannot resolve is not one we can vouch for. `ensure_launchable`
        # treats it as SCAFFOLD, so pre-flight must refuse rather than report an
        # acceptance run as ready — the divergence this docstring promises to avoid.
        if provider is None:
            return RunReadinessCheck(
                code="acquisition_lock_open",
                ok=False,
                detail=(
                    "Code key closed: no acquisition provider could be resolved for this "
                    "source version (unknown provider name in the acquisition spec)."
                ),
            )

        readiness = provider_readiness(provider)
        provider_name = getattr(provider, "provider_name", "unknown")

        if source_version.overlay_id and source_version.provider_template_id:
            try:
                state = await BlueprintEnablementService(self.session).get_state(
                    source_version.overlay_id, source_version.provider_template_id
                )
            except NotFoundError:
                return RunReadinessCheck(
                    code="acquisition_lock_open",
                    ok=False,
                    detail=(
                        f"Blueprint template '{source_version.overlay_id}/"
                        f"{source_version.provider_template_id}' no longer exists."
                    ),
                )
            # Mirrors `_require_launchable`: an operator's explicit close is
            # absolute, a never-turned key is waived for acceptance (#768).
            operator_closed = state.source == "override"
            waive_config_key = for_acceptance and not operator_closed
            # Only a key that was actually shut got waived — an acceptance run
            # over an enabled template must still report both keys turned.
            config_key_waived = waive_config_key and not state.enabled
            if not state.enabled and not waive_config_key:
                detail = (
                    f"Config key closed: template '{source_version.overlay_id}/"
                    f"{source_version.provider_template_id}' is not enabled. "
                )
                # The remedy differs, so the message must too. Telling an operator
                # who deliberately closed the key to "capture evidence" misreads
                # their own kill switch as an un-earned key.
                detail += (
                    "An operator turned this key off; turn it back on from the "
                    "admin panel's Blueprints inventory to run against this portal "
                    "again (ADR-0030)."
                    if operator_closed
                    else "Capture acceptance-run evidence with `mode=acceptance`, "
                    "then enable it (ADR-0030, #632)."
                )
                return RunReadinessCheck(
                    code="acquisition_lock_open",
                    ok=False,
                    detail=detail,
                )
        else:
            # No template to gate on (operator-supplied acquisition spec).
            config_key_waived = False

        # The remedy differs per state, so the detail must too: telling an
        # operator "escalate to engineering" about a finished provider is the
        # misdirection #743 exists to remove.
        if readiness is AcquisitionReadiness.SCAFFOLD:
            return RunReadinessCheck(
                code="acquisition_lock_open",
                ok=False,
                detail=(
                    f"Code key closed: provider '{provider_name}' cannot acquire its "
                    "targets yet. This needs engineering."
                ),
            )
        if readiness is AcquisitionReadiness.AWAITING_EVIDENCE and not for_acceptance:
            return RunReadinessCheck(
                code="acquisition_lock_open",
                ok=False,
                detail=(
                    f"Code key closed: provider '{provider_name}' is implemented but "
                    "has no acceptance-run evidence yet. Dispatch a run with "
                    "mode=acceptance to capture it — this does not need an engineer "
                    "(ADR-0030)."
                ),
            )

        # A rehearsal is any acceptance run where at least one key is not actually
        # turned — either the config key was waived, or the code key is admitted
        # rather than open. Reporting "both keys are turned" for those overstates
        # the lock, which is the class of claim ADR-0030 exists to prevent.
        code_key_admitted = readiness is AcquisitionReadiness.AWAITING_EVIDENCE
        if config_key_waived or (for_acceptance and code_key_admitted):
            unturned = []
            if config_key_waived:
                unturned.append("the config key has never been turned")
            if code_key_admitted:
                unturned.append("the provider has no acceptance evidence yet")
            return RunReadinessCheck(
                code="acquisition_lock_open",
                ok=True,
                detail=(
                    f"Acceptance run: provider '{provider_name}' is implemented, so it may "
                    f"reach the live portal to produce evidence ({', and '.join(unturned)}). "
                    "This is not a production run and does not imply either ADR-0030 key "
                    "is turned."
                ),
            )
        return RunReadinessCheck(
            code="acquisition_lock_open",
            ok=True,
            detail="Both ADR-0030 keys are turned: template enabled and provider live-ready.",
        )

    async def dispatch_pending_runs(self, limit: int = 10) -> int:
        if self.provider is None and self.provider_registry is None:
            raise ProviderConfigurationError(
                "A provider or provider registry is required before dispatching runs."
            )

        pending_runs = list(
            await self.session.scalars(
                select(Run)
                .where(Run.status == RunStatus.PENDING)
                .order_by(Run.created_at.asc())
                .limit(limit)
            )
        )
        dispatched = 0
        pending_publications: list[PendingDispatchPublications] = []
        locked = 0
        for run in pending_runs:
            source = await self.session.get(Source, run.source_id)
            source_version = await self.session.get(SourceVersion, run.source_version_id)
            if source is None or source_version is None:
                continue
            try:
                pending_publications.append(await self._dispatch_run(source, source_version, run))
            except (BlueprintTemplateNotEnabledError, ProviderNotLiveReadyError) as exc:
                # A run the two-key lock rejects can never succeed — fail it instead
                # of leaving it PENDING, or the worker retries it every poll cycle.
                run.status = RunStatus.FAILED
                run.failure_reason = str(exc)
                run.completed_at = datetime.now(UTC)
                locked += 1
                continue
            except Exception as exc:
                # An acceptance run is a ONE-SHOT rehearsal by construction, and it
                # is the one mode whose config key may be waived — so a PENDING
                # acceptance run that keeps throwing is re-dispatched every poll
                # cycle and the operator's `enabled: false` cannot stop it. That is
                # a second route to unattended repetition, alongside the schedule
                # ban ADR-0030 §6 relies on. Terminate it here; the operator can
                # inspect the failure and dispatch a fresh one deliberately.
                if run.mode is not RunMode.ACCEPTANCE:
                    raise
                run.status = RunStatus.FAILED
                run.failure_reason = f"Acceptance run failed and is not retried: {exc}"
                run.completed_at = datetime.now(UTC)
                locked += 1
                continue
            dispatched += 1

        if dispatched > 0 or locked > 0:
            await self.session.commit()
        if dispatched > 0:
            await self._publish_pending_dispatch_events(pending_publications)
        return dispatched

    async def get_run(self, run_id: str) -> Run:
        run = await self.session.get(Run, run_id)
        if run is None:
            raise NotFoundError(f"Run not found: {run_id}")
        return run

    async def list_captured_resources(
        self,
        run_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> CapturedResourceListResponse:
        await self.get_run(run_id)
        total_stmt = (
            select(func.count())
            .select_from(CapturedResource)
            .where(CapturedResource.run_id == run_id)
        )
        total = int((await self.session.execute(total_stmt)).scalar_one())
        result = await self.session.scalars(
            select(CapturedResource)
            .where(CapturedResource.run_id == run_id)
            .order_by(CapturedResource.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        data = [CapturedResourceResponse.model_validate(resource) for resource in result]
        return CapturedResourceListResponse(data=data, total=total, limit=limit, offset=offset)

    async def list_raw_artifacts(
        self,
        run_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> RawArtifactListResponse:
        await self.get_run(run_id)
        total_stmt = (
            select(func.count()).select_from(RawArtifact).where(RawArtifact.run_id == run_id)
        )
        total = int((await self.session.execute(total_stmt)).scalar_one())
        result = await self.session.scalars(
            select(RawArtifact)
            .where(RawArtifact.run_id == run_id)
            .order_by(RawArtifact.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        data = [RawArtifactResponse.model_validate(artifact) for artifact in result]
        return RawArtifactListResponse(data=data, total=total, limit=limit, offset=offset)

    async def list_provider_jobs(
        self,
        run_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> ProviderJobListResponse:
        await self.get_run(run_id)
        total_stmt = (
            select(func.count()).select_from(ProviderJob).where(ProviderJob.run_id == run_id)
        )
        total = int((await self.session.execute(total_stmt)).scalar_one())
        result = await self.session.scalars(
            select(ProviderJob)
            .where(ProviderJob.run_id == run_id)
            .order_by(ProviderJob.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        data = [ProviderJobResponse.model_validate(job) for job in result]
        return ProviderJobListResponse(data=data, total=total, limit=limit, offset=offset)

    async def cancel_run(self, run_id: str) -> Run:
        run = await self.get_run(run_id)
        if run.status not in {RunStatus.PENDING, RunStatus.RUNNING}:
            raise InvalidStateTransitionError(f"Cannot cancel run in status {run.status}.")

        run.status = RunStatus.CANCELLED
        run.completed_at = datetime.now(UTC)
        if run.failure_reason is None:
            run.failure_reason = "Cancelled by operator."
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def retry_run(self, run_id: str) -> Run:
        """Reset a failed or cancelled run.

        Drops provider jobs for the run (and clears resource FKs) so a new dispatch cannot hit
        duplicate ``external_job_id``. Inline backend re-dispatches immediately (typically RUNNING);
        worker backend leaves PENDING for ``dispatch_pending_runs``.
        """
        run = await self.get_run(run_id)
        if run.status not in {RunStatus.FAILED, RunStatus.CANCELLED}:
            raise InvalidStateTransitionError(
                f"Cannot retry run in status {run.status}."
                " Only failed or cancelled runs can be retried."
            )

        run.status = RunStatus.PENDING
        run.started_at = None
        run.completed_at = None
        run.failure_reason = None

        await self.session.execute(
            update(CapturedResource)
            .where(CapturedResource.run_id == run.run_id)
            .where(CapturedResource.provider_job_id.is_not(None))
            .values(provider_job_id=None)
        )
        await self.session.execute(delete(ProviderJob).where(ProviderJob.run_id == run.run_id))
        await self.session.flush()

        if self.run_dispatch_backend != "worker":
            source = await self.session.get(Source, run.source_id)
            source_version = await self.session.get(SourceVersion, run.source_version_id)
            if source and source_version:
                pending_publications = await self._dispatch_run(source, source_version, run)
                await self.session.commit()
                await self.session.refresh(run)
                publish_failures = await self._publish_pending_dispatch_events(
                    [pending_publications]
                )
                if publish_failures:
                    await self.session.refresh(run)
                    raise DispatchPublishError(run.failure_reason or "; ".join(publish_failures))
                return run

        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def get_preview_summary(self, run_id: str) -> RunPreviewSummaryResponse:
        run = await self.get_run(run_id)
        resources = list(
            await self.session.scalars(
                select(CapturedResource)
                .where(CapturedResource.run_id == run_id)
                .order_by(CapturedResource.created_at.asc())
            )
        )

        content_type_counts: dict[str, int] = {}
        checksum_counts = {
            checksum: count
            for checksum, count in (
                await self.session.execute(
                    select(
                        CapturedResource.checksum,
                        func.count(CapturedResource.captured_resource_id),
                    )
                    .where(CapturedResource.run_id == run_id)
                    .where(CapturedResource.checksum.is_not(None))
                    .group_by(CapturedResource.checksum)
                )
            ).all()
            if checksum is not None
        }

        decision_pages: list[RunPreviewSummarySample] = []
        boilerplate_pages: list[RunPreviewSummarySample] = []
        duplicate_pages: list[RunPreviewSummarySample] = []
        distinct_urls: set[str] = set()
        pdf_count = 0

        for resource in resources:
            content_type_counts[resource.content_type] = (
                content_type_counts.get(resource.content_type, 0) + 1
            )
            distinct_urls.add(resource.final_url)

            if self._is_pdf(resource):
                pdf_count += 1
            if self._looks_like_decision(resource):
                decision_pages.append(self._to_summary_sample(resource, "decision_heuristic"))
            if self._looks_like_boilerplate(resource):
                boilerplate_pages.append(self._to_summary_sample(resource, "boilerplate_heuristic"))
            if resource.checksum and checksum_counts.get(resource.checksum, 0) > 1:
                duplicate_pages.append(self._to_summary_sample(resource, "checksum_duplicate"))

        drift_checks = [
            self._drift_check(
                "artifact-count",
                run.artifacts_count > 0,
                "At least one artifact was captured for the run.",
                "No artifacts were captured for the run.",
            ),
            self._drift_check(
                "captured-resource-count",
                run.captured_resources_count > 0,
                "Captured resources were recorded for the run.",
                "No captured resources were recorded for the run.",
            ),
            self._drift_check(
                "content-types-known",
                bool(content_type_counts),
                "Content types were observed for captured resources.",
                "No content types were recorded for captured resources.",
            ),
        ]

        return RunPreviewSummaryResponse(
            run_id=run.run_id,
            captured_url_count=len(distinct_urls),
            artifacts_count=run.artifacts_count,
            captured_resources_count=run.captured_resources_count,
            pdf_count=pdf_count,
            likely_decision_page_count=len(decision_pages),
            likely_boilerplate_page_count=len(boilerplate_pages),
            likely_duplicate_page_count=len(duplicate_pages),
            content_type_breakdown=[
                RunPreviewSummaryBreakdownEntry(content_type=content_type, count=count)
                for content_type, count in sorted(
                    content_type_counts.items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ],
            likely_decision_pages=decision_pages[:10],
            likely_boilerplate_pages=boilerplate_pages[:10],
            likely_duplicate_pages=duplicate_pages[:10],
            drift_checks=drift_checks,
        )

    async def get_pipeline_health(self, run_id: str) -> RunPipelineHealthResponse:
        run = await self.get_run(run_id)
        processing_updates = list(
            await self.session.scalars(
                select(ProcessingStatusUpdate)
                .where(ProcessingStatusUpdate.run_id == run_id)
                .order_by(ProcessingStatusUpdate.occurred_at.desc())
            )
        )
        lifecycle_events = list(
            await self.session.scalars(
                select(DocumentLifecycleEvent)
                .where(DocumentLifecycleEvent.run_id == run_id)
                .order_by(DocumentLifecycleEvent.occurred_at.desc())
            )
        )
        latest_processing = processing_updates[0] if processing_updates else None
        latest_lifecycle = lifecycle_events[0] if lifecycle_events else None

        acquisition_stage = self._resolve_acquisition_stage(run)
        di_stage = self._resolve_di_stage(run, latest_processing)
        projection_stage = self._resolve_projection_stage(latest_processing, latest_lifecycle)
        search_stage = self._resolve_search_stage(latest_lifecycle)

        stages = [acquisition_stage, di_stage, projection_stage, search_stage]
        overall_status = self._resolve_overall_pipeline_status(stages)

        return RunPipelineHealthResponse(
            run_id=run.run_id,
            source_id=run.source_id,
            source_version_id=run.source_version_id,
            mode=run.mode,
            run_status=run.status,
            overall_status=overall_status,
            stages=stages,
            processing_status_event_count=len(processing_updates),
            document_lifecycle_event_count=len(lifecycle_events),
        )

    async def get_provider_job_by_external_id(self, external_job_id: str) -> ProviderJob | None:
        return await self.session.scalar(
            select(ProviderJob).where(ProviderJob.external_job_id == external_job_id)
        )

    @staticmethod
    def _validate_version_for_run_mode(source_version: SourceVersion, run_mode: RunMode) -> None:
        if (
            run_mode is RunMode.PRODUCTION
            and source_version.status is not SourceVersionStatus.APPROVED
        ):
            raise InvalidStateTransitionError("Production runs require an approved source version.")
        if source_version.status in {
            SourceVersionStatus.REJECTED,
            SourceVersionStatus.SUPERSEDED,
        }:
            raise InvalidStateTransitionError(
                f"Cannot create runs from source versions in status {source_version.status}."
            )

    @classmethod
    def assess_run_readiness(
        cls,
        *,
        source: Source | None,
        source_version: SourceVersion | None,
        source_id: str,
        source_version_id: str,
        mode: RunMode,
    ) -> RunReadinessResponse:
        checks: list[RunReadinessCheck] = []

        checks.append(
            RunReadinessCheck(
                code="source_exists",
                ok=source is not None,
                detail=(
                    "Source exists." if source is not None else f"Source not found: {source_id}."
                ),
            )
        )
        checks.append(
            RunReadinessCheck(
                code="source_version_exists",
                ok=source_version is not None,
                detail=(
                    "Source version exists."
                    if source_version is not None
                    else f"Source version not found: {source_version_id}."
                ),
            )
        )

        belongs_to_source = (
            source is not None
            and source_version is not None
            and source_version.source_id == source.source_id
        )
        checks.append(
            RunReadinessCheck(
                code="source_version_belongs_to_source",
                ok=belongs_to_source,
                detail=(
                    "Source version belongs to source."
                    if belongs_to_source
                    else "Source version does not belong to the requested source."
                ),
            )
        )

        mode_compatible = False
        mode_detail = "Cannot determine mode compatibility before source/version checks pass."
        if belongs_to_source and source_version is not None:
            try:
                cls._validate_version_for_run_mode(source_version, mode)
                mode_compatible = True
                mode_detail = "Version status is compatible with requested run mode."
            except InvalidStateTransitionError as exc:
                mode_detail = str(exc)
        checks.append(
            RunReadinessCheck(
                code="mode_compatible_with_version_status",
                ok=mode_compatible,
                detail=mode_detail,
            )
        )

        has_seed = False
        seed_detail = "Cannot determine acquisition seeds before source/version checks pass."
        if belongs_to_source and source_version is not None:
            acquisition_spec = source_version.acquisition_spec or {}
            seed_url = acquisition_spec.get("seed_url")
            seed_urls = acquisition_spec.get("seed_urls")
            base_url = acquisition_spec.get("base_url")
            code_ids = acquisition_spec.get("code_ids")
            normalized_seed_url = seed_url.strip() if isinstance(seed_url, str) else ""
            normalized_seed_urls = (
                [url.strip() for url in seed_urls if isinstance(url, str) and url.strip()]
                if isinstance(seed_urls, list)
                else []
            )
            normalized_base_url = base_url.strip() if isinstance(base_url, str) else ""
            provider_name = acquisition_spec.get("provider")
            normalized_code_ids = (
                [
                    code_id.strip()
                    for code_id in code_ids
                    if isinstance(code_id, str) and code_id.strip()
                ]
                if provider_name == "legifrance" and isinstance(code_ids, list)
                else []
            )
            # Not every provider discovers from a URL. Readiness that only knows
            # how to look for seeds refuses a correctly-configured source and
            # tells the operator to add a field their provider does not take —
            # that is #706, where readiness demanded seeds the platform's own
            # blueprint emits empty. Each entry names the field that provider
            # actually needs, and the refusal message says so.
            #
            # This is the second such provider. A third should stop the table
            # growing and ask the provider itself: `ProviderPlan` already
            # reports what a run would execute without touching the network.
            discovery_key = _QUERY_DISCOVERY_KEY_BY_PROVIDER.get(provider_name or "")
            normalized_discovery_value = ""
            if discovery_key:
                raw = acquisition_spec.get(discovery_key)
                normalized_discovery_value = raw.strip() if isinstance(raw, str) else ""

            # An enumerating spec has no query and no seed and is still perfectly
            # launchable: it walks the source's own key space rather than asking it a
            # question (#816). Without this, `enumeration: systematic_digit_union`
            # is refused at preflight for missing the `search_text` it does not use.
            normalized_enumeration = (
                acquisition_spec.get("enumeration")
                if isinstance(acquisition_spec.get("enumeration"), str)
                else ""
            )

            has_seed = bool(
                normalized_seed_url
                or normalized_seed_urls
                or normalized_base_url
                or normalized_code_ids
                or normalized_discovery_value
                or normalized_enumeration
            )
            if normalized_enumeration:
                seed_detail = (
                    f"Acquisition spec enumerates the source's key space "
                    f"('{normalized_enumeration}'), so it needs no seed or query."
                )
            elif has_seed:
                seed_detail = (
                    "Acquisition spec has at least one seed, base URL, or provider-specific seed."
                )
            elif provider_name == "legifrance":
                seed_detail = "Legifrance acquisition spec must define code_ids."
            elif discovery_key:
                seed_detail = (
                    f"Provider '{provider_name}' discovers by query, not by URL: its "
                    f"acquisition spec must define a non-empty '{discovery_key}'. "
                    "Seed URLs are not used and will not satisfy this check."
                )
            else:
                seed_detail = "Acquisition spec must define seed_url, seed_urls, or base_url."
        checks.append(
            RunReadinessCheck(
                code="acquisition_seed_present",
                ok=has_seed,
                detail=seed_detail,
            )
        )

        return RunReadinessResponse(
            source_id=source_id,
            source_version_id=source_version_id,
            mode=mode,
            ready=all(check.ok for check in checks),
            checks=checks,
        )

    @staticmethod
    def _to_summary_sample(resource: CapturedResource, reason: str) -> RunPreviewSummarySample:
        return RunPreviewSummarySample(
            captured_resource_id=resource.captured_resource_id,
            title=resource.title,
            final_url=resource.final_url,
            content_type=resource.content_type,
            http_status=resource.http_status,
            reason=reason,
        )

    @classmethod
    def _looks_like_decision(cls, resource: CapturedResource) -> bool:
        haystack = " ".join(filter(None, [resource.title, resource.final_url, resource.source_url]))
        return bool(cls._DECISION_PATTERN.search(haystack))

    @classmethod
    def _looks_like_boilerplate(cls, resource: CapturedResource) -> bool:
        haystack = " ".join(filter(None, [resource.title, resource.final_url, resource.source_url]))
        return bool(cls._BOILERPLATE_PATTERN.search(haystack))

    @staticmethod
    def _is_pdf(resource: CapturedResource) -> bool:
        return resource.content_type == "application/pdf" or resource.final_url.lower().endswith(
            ".pdf"
        )

    @staticmethod
    def _drift_check(
        name: str,
        ok: bool,
        success: str,
        failure: str,
    ) -> RunPreviewSummaryDriftCheck:
        return RunPreviewSummaryDriftCheck(
            name=name,
            status="ok" if ok else "warn",
            detail=success if ok else failure,
        )

    @staticmethod
    def _resolve_acquisition_stage(run: Run) -> RunPipelineHealthStage:
        status_map = {
            RunStatus.PENDING: ("pending", "Run accepted and waiting for acquisition dispatch."),
            RunStatus.RUNNING: ("in_progress", "Acquisition provider run is in progress."),
            RunStatus.COMPLETED: ("ok", "Acquisition/provider stage completed."),
            RunStatus.FAILED: ("failed", run.failure_reason or "Run failed during acquisition."),
            RunStatus.CANCELLED: (
                "blocked",
                run.failure_reason or "Run was cancelled before pipeline completion.",
            ),
        }
        stage_status, detail = status_map[run.status]
        updated_at = run.completed_at or run.started_at or run.updated_at
        return RunPipelineHealthStage(
            stage="acquisition",
            status=stage_status,
            detail=detail,
            updated_at=updated_at,
        )

    @staticmethod
    def _resolve_di_stage(
        run: Run, latest_processing: ProcessingStatusUpdate | None
    ) -> RunPipelineHealthStage:
        if latest_processing is None:
            if run.status in {RunStatus.FAILED, RunStatus.CANCELLED}:
                return RunPipelineHealthStage(
                    stage="document_intelligence",
                    status="blocked",
                    detail="No processing status events were received after terminal run status.",
                    updated_at=run.completed_at or run.updated_at,
                )
            return RunPipelineHealthStage(
                stage="document_intelligence",
                status="pending",
                detail="Awaiting first document-intelligence processing status event.",
                updated_at=None,
            )

        if latest_processing.status.value == "failed":
            status = "failed"
            detail = latest_processing.error_summary or "Document-intelligence processing failed."
        elif latest_processing.status.value in {"accepted", "processing"}:
            status = "in_progress"
            detail = f"Latest processing status is {latest_processing.status.value}."
        else:
            status = "ok"
            detail = f"Latest processing status is {latest_processing.status.value}."
        return RunPipelineHealthStage(
            stage="document_intelligence",
            status=status,
            detail=detail,
            updated_at=latest_processing.occurred_at,
        )

    @staticmethod
    def _resolve_projection_stage(
        latest_processing: ProcessingStatusUpdate | None,
        latest_lifecycle: DocumentLifecycleEvent | None,
    ) -> RunPipelineHealthStage:
        if latest_lifecycle is not None:
            return RunPipelineHealthStage(
                stage="projection",
                status="ok",
                detail=(
                    f"Latest lifecycle event `{latest_lifecycle.event_type}`"
                    f" (status={latest_lifecycle.lifecycle_status or 'n/a'})."
                ),
                updated_at=latest_lifecycle.occurred_at,
            )
        if latest_processing is None:
            return RunPipelineHealthStage(
                stage="projection",
                status="pending",
                detail="Awaiting DI processing signal before projection stage starts.",
                updated_at=None,
            )
        if latest_processing.status.value == "failed":
            return RunPipelineHealthStage(
                stage="projection",
                status="blocked",
                detail="Projection blocked because DI reported a failed status.",
                updated_at=latest_processing.occurred_at,
            )
        return RunPipelineHealthStage(
            stage="projection",
            status="in_progress",
            detail=(
                "DI has emitted status updates; waiting for document lifecycle projection events."
            ),
            updated_at=latest_processing.occurred_at,
        )

    @staticmethod
    def _resolve_search_stage(
        latest_lifecycle: DocumentLifecycleEvent | None,
    ) -> RunPipelineHealthStage:
        if latest_lifecycle is None:
            return RunPipelineHealthStage(
                stage="search",
                status="pending",
                detail=(
                    "Awaiting projection lifecycle events before search indexing/disposition is "
                    "confirmed."
                ),
                updated_at=None,
            )
        if latest_lifecycle.search_disposition == "remove":
            detail = "Latest lifecycle indicates search removal/de-index disposition."
        else:
            detail = "Latest lifecycle indicates searchable projection path is active."
        return RunPipelineHealthStage(
            stage="search",
            status="ok",
            detail=detail,
            updated_at=latest_lifecycle.occurred_at,
        )

    @staticmethod
    def _resolve_overall_pipeline_status(stages: list[RunPipelineHealthStage]) -> str:
        if any(stage.status == "failed" for stage in stages):
            return "failed"
        if any(stage.status == "blocked" for stage in stages):
            return "blocked"
        if any(stage.status in {"pending", "in_progress"} for stage in stages):
            return "in_progress"
        return "ok"

    async def _dispatch_run(
        self,
        source: Source,
        source_version: SourceVersion,
        run: Run,
    ) -> PendingDispatchPublications:
        provider = self.provider
        if provider is None and self.provider_registry is not None:
            provider = self.provider_registry.resolve_for_version(source_version)
        if provider is None:
            raise ProviderConfigurationError(
                "An acquisition provider or provider registry is required before creating runs."
            )

        # Last gate before any outbound request: no scaffold provider and no
        # disabled blueprint template may reach a live portal (ADR-0030). The run
        # carries its own mode, so an acceptance run re-checks as an acceptance run
        # here — otherwise dispatch would refuse what creation admitted.
        await self._require_launchable(source_version, provider, run.mode)

        # Bind the jurisdiction's rate limiter + robots context into the async
        # context so every outbound GET performed by the provider honours them.
        # set/reset keeps concurrent runs on different policies isolated.
        limiter = await resolve_rate_limiter_for_source(
            self.session, source, self.rate_limiter_registry
        )
        robots_ctx = await resolve_robots_context_for_source(
            self.session, source, self.robots_checker
        )
        limiter_token = current_rate_limiter.set(limiter)
        robots_token = current_robots_context.set(robots_ctx)
        try:
            provider_result = await provider.start_run(source, source_version, run)
        finally:
            current_robots_context.reset(robots_token)
            current_rate_limiter.reset(limiter_token)
        provider_job = ProviderJob(
            run_id=run.run_id,
            provider=provider_result.provider,
            external_job_id=provider_result.external_job_id,
            status=ProviderJobStatus.ACCEPTED,
            request_payload=provider_result.request_payload,
            response_payload=provider_result.response_payload,
        )
        self.session.add(provider_job)
        run.status = RunStatus.RUNNING
        run.started_at = datetime.now(UTC)
        # Funnel stage 1. Every launch path (API, connector worker, Temporal activity)
        # converges on _dispatch_run, so one counter here covers all three.
        metrics.record_run_launched(provider_job.provider)
        pending_publications = PendingDispatchPublications(run_id=run.run_id)

        if provider_result.inline_resources:
            pending_publications.raw_artifact_ids.extend(
                await self._persist_inline_resources(
                    run=run,
                    source=source,
                    source_version=source_version,
                    provider_job=provider_job,
                    resources=provider_result.inline_resources,
                )
            )
            bundle_events = await self._build_per_document_bundle_events(
                run=run,
                source=source,
                source_version=source_version,
            )
            for bundle_event in bundle_events:
                pending_publications.bundle_events.append(bundle_event)
            if bundle_events:
                await self.artifact_store.store_page_payload(
                    run.run_id,
                    "bundle_events",
                    {"count": len(bundle_events), "events": bundle_events},
                )
            provider_job.status = ProviderJobStatus.COMPLETED
            provider_job.last_event_type = "inline.completed"
            run.status = RunStatus.COMPLETED
            run.completed_at = datetime.now(UTC)

        if provider_result.inline_failure_reason:
            provider_job.status = ProviderJobStatus.FAILED
            provider_job.last_event_type = "inline.failed"
            run.status = RunStatus.FAILED
            run.completed_at = datetime.now(UTC)
            run.failure_reason = provider_result.inline_failure_reason

        self._record_coverage_reconciliation(
            run=run,
            source=source,
            source_version=source_version,
            provider_job=provider_job,
            response_payload=provider_result.response_payload,
        )

        if run.status is RunStatus.RUNNING:
            # The run is now in the provider's hands and will only ever complete via a
            # webhook (Firecrawl) or a later poll. Commit the ProviderJob immediately
            # instead of leaving it to the caller: until it is committed, an inbound
            # `crawl.started` cannot resolve external_job_id -> run. Callers hold the
            # transaction open for a while — `dispatch_pending_runs` batches up to 10
            # runs before one commit — so the window is wide (#558).
            #
            # This narrows the race but cannot close it: `external_job_id` is minted by
            # the provider, so no row can exist before the POST returns, and Firecrawl
            # may fire `crawl.started` while that response is still in flight. The
            # webhook handler therefore also treats an unmatched job as retryable rather
            # than consuming it.
            await self.session.commit()
        return pending_publications

    def _record_coverage_reconciliation(
        self,
        *,
        run: Run,
        source: Source,
        source_version: SourceVersion,
        provider_job: ProviderJob,
        response_payload: dict[str, Any],
    ) -> None:
        """Persist a run's coverage measurement, if it reported one (#816).

        Rides this dispatch's transaction on purpose. The row is derived from the SAME
        in-memory payload object that becomes `provider_job.response_payload`, so the two
        cannot drift — there is no re-read and no second code path where they could.

        Attribution comes from `source.jurisdiction_id`, captured now rather than resolved
        at read time: a source later re-pointed at another jurisdiction must not
        retroactively re-attribute this measurement.
        """
        parsed = parse_coverage_payload(response_payload)
        if parsed is None:
            return

        attributed = parsed.attribution_status is CoverageAttributionStatus.ATTRIBUTED
        self.session.add(
            CoverageReconciliation(
                run_id=run.run_id,
                source_id=source.source_id,
                source_version_id=source_version.source_version_id,
                # `provider_job_id` comes from a column default evaluated at flush, so it
                # is still None here. Flushing just to read it would buy nothing: the FK
                # is nullable precisely so this row can be added in the same unit of work,
                # and the payload it was distilled from is reachable via `run_id` anyway.
                provider_job_id=None,
                jurisdiction_id=source.jurisdiction_id if attributed else None,
                attribution_status=parsed.attribution_status,
                entity_id=parsed.entity_id,
                strategy=parsed.strategy,
                denominator_tier=parsed.denominator_tier,
                denominator_source=parsed.denominator_source,
                expected=parsed.expected,
                observed=parsed.observed,
                provider_complete_claim=parsed.provider_complete_claim,
                truncated=parsed.truncated,
                run_mode=run.mode,
                as_of=parsed.as_of,
            )
        )

    async def _persist_inline_resources(
        self,
        *,
        run: Run,
        source: Source,
        source_version: SourceVersion,
        provider_job: ProviderJob,
        resources: list[ProviderResource],
    ) -> list[str]:
        pipeline = ArtifactPipeline()
        normalized_pairs = pipeline.normalize(run_id=run.run_id, resources=resources)
        artifact_ids: list[str] = []
        for raw_record, captured_record in normalized_pairs:
            artifact = RawArtifact(
                run_id=run.run_id,
                source_id=source.source_id,
                source_version_id=source_version.source_version_id,
                storage_path="",
                content_type=raw_record.content_type,
                artifact_metadata={},
            )
            self.session.add(artifact)
            await self.session.flush()
            payload = dict(raw_record.metadata)
            payload_bytes = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
            artifact.storage_path = await self.artifact_store.store_page_payload(
                run_id=run.run_id,
                artifact_id=artifact.artifact_id,
                payload=payload,
            )
            artifact.artifact_metadata = {
                **payload,
                "title": captured_record.title,
                "byte_size": len(payload_bytes),
                "checksum": hashlib.sha256(payload_bytes).hexdigest(),
                "checksum_algorithm": "sha256",
            }
            self.session.add(
                CapturedResource(
                    artifact_id=artifact.artifact_id,
                    run_id=run.run_id,
                    source_id=source.source_id,
                    source_version_id=source_version.source_version_id,
                    provider_job_id=provider_job.provider_job_id,
                    provider=provider_job.provider,
                    source_url=captured_record.source_url,
                    final_url=captured_record.final_url,
                    title=captured_record.title,
                    content_type=captured_record.content_type,
                    checksum=captured_record.checksum,
                    http_status=captured_record.http_status,
                    discovery_depth=captured_record.discovery_depth,
                    resource_metadata=captured_record.metadata,
                )
            )
            run.artifacts_count += 1
            run.captured_resources_count += 1
            metrics.record_artifact_captured("inline")
            artifact_ids.append(artifact.artifact_id)
        return artifact_ids

    async def _build_bundle_manifest_event(
        self,
        *,
        run: Run,
        source: Source,
        source_version: SourceVersion,
    ) -> dict[str, Any] | None:
        artifacts = list(
            await self.session.scalars(
                select(RawArtifact)
                .where(RawArtifact.run_id == run.run_id)
                .order_by(RawArtifact.created_at.asc())
            )
        )
        if not artifacts:
            return None

        source_snapshot_id = generate_prefixed_id("snap")
        bundle_manifest_id = generate_prefixed_id("abm")
        upstream_locator = self._upstream_locator(artifacts[0].artifact_metadata)

        roles: list[str] = []
        for index, artifact in enumerate(artifacts):
            if artifact.content_type.startswith("application/json"):
                roles.append("metadata")
            elif index == 0:
                roles.append("primary_document")
            else:
                roles.append("attachment")
        # JSON-only bundles (e.g. deterministic_http on application/json URLs) must still expose a
        # primary_document so document-intelligence can load the bundle.
        if roles and "primary_document" not in roles:
            roles[0] = "primary_document"

        manifest_artifacts: list[dict[str, Any]] = []
        for artifact, role in zip(artifacts, roles, strict=True):
            manifest_artifacts.append(
                {
                    "artifact_id": artifact.artifact_id,
                    "artifact_role": role,
                    "storage_ref": self._build_storage_ref_for_artifact(artifact),
                }
            )

        acquisition_spec = source_version.acquisition_spec or {}
        tenant_id = str(acquisition_spec.get("tenant_id") or "tenant_public")
        corpus_id = str(acquisition_spec.get("corpus_id") or f"corpus_{source.jurisdiction_id}")
        scope_type = str(acquisition_spec.get("scope_type") or "global_public")
        source_origin_kind = str(acquisition_spec.get("source_origin_kind") or "official_primary")
        trust_tier = str(acquisition_spec.get("trust_tier") or "authoritative")
        authority_name = await self._resolve_authority_name(source.authority_id)
        attribution = await self._resolve_attribution(source.jurisdiction_id)

        manifest = build_artifact_bundle_manifest(
            bundle_manifest_id=bundle_manifest_id,
            source_snapshot_id=source_snapshot_id,
            source_id=source.source_id,
            source_version_id=source_version.source_version_id,
            run_id=run.run_id,
            jurisdiction_id=source.jurisdiction_id,
            authority_id=source.authority_id,
            authority_name=authority_name,
            upstream_locator=upstream_locator,
            artifacts=manifest_artifacts,
            tenant_id=tenant_id,
            corpus_id=corpus_id,
            scope_type=scope_type,
            source_origin_kind=source_origin_kind,
            trust_tier=trust_tier,
            language_codes=acquisition_spec.get("language_codes") or [],
            document_type_hint=acquisition_spec.get("document_type_hint"),
            bundle_metadata={
                "extraction_hints": build_bundle_extraction_hints(
                    artifact_metadata=artifacts[0].artifact_metadata,
                    document_type_hint=acquisition_spec.get("document_type_hint"),
                    authority_display_hint=authority_name,
                ),
            },
            attribution=attribution,
            snapshot_captured_at=run.completed_at or datetime.now(UTC),
        )
        reference_snapshot_set = self._build_reference_snapshot_set(
            source=source,
            source_version=source_version,
            run=run,
            manifest_provenance=manifest["provenance"],
        )
        reference_snapshot_set_id = str(reference_snapshot_set["reference_snapshot_set_id"])
        reference_snapshot_storage_ref = await self.artifact_store.store_bundle_manifest(
            run_id=run.run_id,
            bundle_manifest_id=reference_snapshot_set_id,
            payload=reference_snapshot_set,
        )
        manifest.setdefault("bundle_metadata", {})
        manifest["bundle_metadata"]["reference_snapshot_export"] = {
            "reference_snapshot_set_id": reference_snapshot_set_id,
            "storage_ref": reference_snapshot_storage_ref,
        }
        manifest_storage_ref = await self.artifact_store.store_bundle_manifest(
            run_id=run.run_id,
            bundle_manifest_id=bundle_manifest_id,
            payload=manifest,
        )
        manifest_ref = {
            "manifest_id": bundle_manifest_id,
            "manifest_type": "artifact_bundle_manifest",
            "manifest_version": 1,
            "storage_ref": manifest_storage_ref,
        }
        event = build_artifact_bundle_available_event(
            bundle_manifest_id=bundle_manifest_id,
            source_snapshot_id=source_snapshot_id,
            source_origin_kind=source_origin_kind,
            trust_tier=trust_tier,
            provenance=manifest["provenance"],
            bundle_manifest_ref=manifest_ref,
            correlation_id=run.run_id,
            occurred_at=run.completed_at or datetime.now(UTC),
        )
        return event

    async def _build_per_document_bundle_events(
        self,
        *,
        run: Run,
        source: Source,
        source_version: SourceVersion,
    ) -> list[dict[str, Any]]:
        """Build one bundle event per non-metadata artifact (one document each)."""
        artifacts = list(
            await self.session.scalars(
                select(RawArtifact)
                .where(RawArtifact.run_id == run.run_id)
                .order_by(RawArtifact.created_at.asc())
            )
        )
        if not artifacts:
            return []

        doc_artifacts = [a for a in artifacts if not a.content_type.startswith("application/json")]
        if not doc_artifacts:
            # JSON-only acquisition (e.g. API seeds): still one processable document.
            doc_artifacts = list(artifacts)
        if not doc_artifacts:
            return []

        acquisition_spec = source_version.acquisition_spec or {}
        tenant_id = str(acquisition_spec.get("tenant_id") or "tenant_public")
        corpus_id = str(acquisition_spec.get("corpus_id") or f"corpus_{source.jurisdiction_id}")
        scope_type = str(acquisition_spec.get("scope_type") or "global_public")
        source_origin_kind = str(acquisition_spec.get("source_origin_kind") or "official_primary")
        trust_tier = str(acquisition_spec.get("trust_tier") or "authoritative")
        authority_name = await self._resolve_authority_name(source.authority_id)
        attribution = await self._resolve_attribution(source.jurisdiction_id)

        events: list[dict[str, Any]] = []
        for artifact in doc_artifacts:
            source_snapshot_id = generate_prefixed_id("snap")
            bundle_manifest_id = generate_prefixed_id("abm")
            upstream_locator = self._upstream_locator(artifact.artifact_metadata)

            manifest_artifact = {
                "artifact_id": artifact.artifact_id,
                "artifact_role": "primary_document",
                "storage_ref": self._build_storage_ref_for_artifact(artifact),
            }
            manifest = build_artifact_bundle_manifest(
                bundle_manifest_id=bundle_manifest_id,
                source_snapshot_id=source_snapshot_id,
                source_id=source.source_id,
                source_version_id=source_version.source_version_id,
                run_id=run.run_id,
                jurisdiction_id=source.jurisdiction_id,
                authority_id=source.authority_id,
                authority_name=authority_name,
                upstream_locator=upstream_locator,
                artifacts=[manifest_artifact],
                tenant_id=tenant_id,
                corpus_id=corpus_id,
                scope_type=scope_type,
                source_origin_kind=source_origin_kind,
                trust_tier=trust_tier,
                language_codes=acquisition_spec.get("language_codes") or [],
                document_type_hint=acquisition_spec.get("document_type_hint"),
                bundle_metadata={
                    "extraction_hints": build_bundle_extraction_hints(
                        artifact_metadata=artifact.artifact_metadata,
                        document_type_hint=acquisition_spec.get("document_type_hint"),
                        authority_display_hint=authority_name,
                    ),
                },
                attribution=attribution,
                snapshot_captured_at=run.completed_at or datetime.now(UTC),
            )
            manifest_storage_ref = await self.artifact_store.store_bundle_manifest(
                run_id=run.run_id,
                bundle_manifest_id=bundle_manifest_id,
                payload=manifest,
            )
            manifest_ref = {
                "manifest_id": bundle_manifest_id,
                "manifest_type": "artifact_bundle_manifest",
                "manifest_version": 1,
                "storage_ref": manifest_storage_ref,
            }
            event = build_artifact_bundle_available_event(
                bundle_manifest_id=bundle_manifest_id,
                source_snapshot_id=source_snapshot_id,
                source_origin_kind=source_origin_kind,
                trust_tier=trust_tier,
                provenance=manifest["provenance"],
                bundle_manifest_ref=manifest_ref,
                correlation_id=run.run_id,
                occurred_at=run.completed_at or datetime.now(UTC),
            )
            events.append(event)
        return events

    async def _resolve_authority_name(self, authority_id: str | None) -> str | None:
        if not authority_id:
            return None
        authority = await self.session.get(Authority, authority_id)
        return authority.name if authority is not None else None

    async def _resolve_attribution(self, jurisdiction_id: str | None) -> dict[str, Any] | None:
        """Return the attribution block for the manifest when required.

        Falls back to ``None`` when the jurisdiction has no policy or attribution
        isn't required — callers simply omit the attribution key.
        """
        from platform_control.models.authority import Jurisdiction
        from platform_control.models.compliance_policy import CompliancePolicy

        if not jurisdiction_id:
            return None
        jurisdiction = await self.session.get(Jurisdiction, jurisdiction_id)
        if jurisdiction is None or jurisdiction.compliance_policy_id is None:
            return None
        policy = await self.session.get(CompliancePolicy, jurisdiction.compliance_policy_id)
        if policy is None or not policy.attribution_required:
            return None
        return {
            "required": True,
            "text": policy.attribution_text,
            "contact_url": policy.contact_url,
        }

    async def _publish_pending_dispatch_events(
        self, pending_publications: list[PendingDispatchPublications]
    ) -> list[str]:
        """Hand the dispatched run's events to the broker, honestly (#707).

        Publication happens after the run row is already committed, so a failure
        here used to be invisible: the exception escaped to FastAPI as a bare 500
        while the run kept `status: completed, failure_reason: null` over a pipeline
        that delivered nothing downstream. Acquisition really had succeeded — the
        artifact counts were never fabricated — but no field said the handoff died.

        Two properties this restores, and both are general: they hold for *any*
        publish failure (broker down, subject not bound, oversize payload), not just
        the `MaxPayloadError` that exposed them.

        1. **A run whose events did not publish is not `completed`.** It is rewritten
           to terminal FAILED with a `failure_reason` naming the cause, and a
           `dispatch_publish_failed` marker in `run_metadata` alongside the existing
           `refused` marker (#634/#681) so the trace is machine-readable, not just prose.
        2. **One bad event does not take out its batch.** Each publish is isolated, so
           an artifact that cannot be published no longer strands its siblings — under
           the old loop TSchG, well under the limit, was lost as collateral to TSchV.
           Every event that *can* be delivered still is, and the run is failed anyway,
           because partial delivery is not success either.

        Returns the failure reasons. Callers that answer an operator over HTTP raise
        `DispatchPublishError`; the worker loop keeps going, since each affected run
        already carries its own honest record.
        """
        failures: list[str] = []
        for pending in pending_publications:
            run_failures: list[str] = []
            for artifact_id in pending.raw_artifact_ids:
                artifact = await self.session.get(RawArtifact, artifact_id)
                if artifact is None:  # pragma: no cover - defensive guard
                    continue
                try:
                    await self.publisher.publish_raw_artifact_available(artifact)
                except Exception as exc:
                    run_failures.append(f"raw_artifact.available for {artifact_id}: {exc}")
            for event in pending.bundle_events:
                try:
                    await self.publisher.publish_artifact_bundle_available(event)
                except Exception as exc:
                    run_failures.append(
                        f"artifact_bundle.available for {event.get('event_id')}: {exc}"
                    )
                    continue
                metrics.record_bundle_event_published()
            if run_failures:
                await self._record_dispatch_publish_failure(pending.run_id, run_failures)
                failures.extend(run_failures)
        return failures

    async def _record_dispatch_publish_failure(
        self, run_id: str | None, run_failures: list[str]
    ) -> None:
        """Rewrite a run that acquired successfully but could not hand off (#707)."""
        reason = (
            "Acquisition succeeded but the downstream handoff failed, so"
            " document-intelligence received nothing from this run."
            f" {len(run_failures)} event(s) could not be published: "
            + "; ".join(run_failures)
            + ". The captured artifacts are stored and the run can be retried"
            " once the cause is resolved."
        )
        logging.getLogger(__name__).error(
            "dispatch publish failed for run %s: %s", run_id, "; ".join(run_failures)
        )
        if run_id is None:  # pragma: no cover - defensive guard
            return
        run = await self.session.get(Run, run_id)
        if run is None:  # pragma: no cover - defensive guard
            return
        run.status = RunStatus.FAILED
        run.failure_reason = reason
        run.completed_at = datetime.now(UTC)
        run.run_metadata = {**(run.run_metadata or {}), "dispatch_publish_failed": True}
        await self.session.commit()

    @staticmethod
    def _upstream_locator(artifact_metadata: dict[str, Any]) -> str:
        """The locator `document_id` is derived from (#652, #806).

        `document_intelligence`'s `_document_identity_key` keys `document_id` on this
        string, and the projection upserts on `document_id`
        (`opensearch.adapter.ts` `upsertProjection`). Two properties therefore matter.

        **`source_url` must stay ahead of `final_url`.** They are different URIs by
        construction for the SPARQL providers, not merely on redirect: `fedlex_sparql`
        sets `source_url` to the act-level ELI (`.../eli/cc/1999/404`) and `final_url`
        to the filestore manifestation, whose path **embeds the consolidation date**
        (`fedlex_sparql_provider.py` `_filestore_html_url`). Keying on `final_url`
        would mint a fresh `document_id` at every consolidation — the #652 duplicate,
        permanently, across the whole federal corpus. `eur_lex_sparql` is the same
        shape. Do not flip this order globally; see #806 for why the correct identity
        is a per-provider decision (`lexfind_api` needs the opposite preference and is
        wrong today).

        Returns `""` when the artifact carries no URL at all. This must not be a shared
        placeholder: every locator-less artifact of a source would derive one
        `document_id` and silently overwrite itself in the index. Empty defers to
        `_document_identity_key`'s per-artifact fallback — `upstream_locator` is
        neither required nor constrained in `artifact-bundle-manifest.schema.json`.
        """
        return str(artifact_metadata.get("source_url") or artifact_metadata.get("final_url") or "")

    @staticmethod
    def _build_storage_ref_for_artifact(artifact: RawArtifact) -> dict[str, Any]:
        metadata = dict(artifact.artifact_metadata or {})
        payload_bytes = json.dumps(metadata, indent=2, sort_keys=True).encode("utf-8")
        checksum = str(metadata.get("checksum") or hashlib.sha256(payload_bytes).hexdigest())
        return {
            "uri": artifact.storage_path,
            "content_type": artifact.content_type,
            "byte_size": int(metadata.get("byte_size") or len(payload_bytes)),
            "checksum": checksum,
            "checksum_algorithm": "sha256",
            "created_at": artifact.created_at.isoformat(),
        }

    @staticmethod
    def _build_reference_snapshot_set(
        *,
        source: Source,
        source_version: SourceVersion,
        run: Run,
        manifest_provenance: dict[str, Any],
    ) -> dict[str, Any]:
        acquisition_spec = source_version.acquisition_spec or {}
        return {
            "reference_snapshot_set_id": generate_prefixed_id("rss"),
            "generated_at": (run.completed_at or datetime.now(UTC)).isoformat(),
            "provenance": {
                "run_id": run.run_id,
                "source_id": source.source_id,
                "source_version_id": source_version.source_version_id,
                "tenant_id": manifest_provenance.get("tenant_id"),
                "corpus_id": manifest_provenance.get("corpus_id"),
                "scope_type": manifest_provenance.get("scope_type"),
            },
            "jurisdictions": [{"jurisdiction_id": source.jurisdiction_id}],
            "authorities": ([{"authority_id": source.authority_id}] if source.authority_id else []),
            "extractor_profile_hint": acquisition_spec.get("extractor_profile_hint"),
            "language_codes": acquisition_spec.get("language_codes") or [],
            "document_type_hint": acquisition_spec.get("document_type_hint"),
        }
