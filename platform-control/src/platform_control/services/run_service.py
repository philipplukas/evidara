from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from acquisition_core.identity import upstream_locator as resolve_upstream_locator
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
    PipelineStageStatus,
    ProviderJobStatus,
    RunMode,
    RunRefusalCode,
    RunStatus,
    SourceVersionStatus,
)
from platform_control.errors import (
    BlueprintTemplateNotEnabledError,
    CompliancePolicyMissingError,
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
from platform_control.models.run import (
    DISPATCH_PUBLISH_WITHHELD_KEY,
    PUBLISHED_ARTIFACTS_COUNT_KEY,
    Run,
    publication_withheld_from,
    published_artifacts_count_from,
)
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
    RunDecisionNote,
    RunDecisionSupport,
    RunListItemResponse,
    RunPipelineHealthResponse,
    RunPipelineHealthStage,
    RunPreviewSummaryBreakdownEntry,
    RunPreviewSummaryDriftCheck,
    RunPreviewSummaryResponse,
    RunPreviewSummarySample,
    RunReadinessCheck,
    RunReadinessResponse,
    RunStageAction,
)
from platform_control.services.acquisition_provider import AcquisitionProvider, ProviderResource
from platform_control.services.artifact_store import ArtifactStore
from platform_control.services.blueprint_enablement import BlueprintEnablementService
from platform_control.services.compliance_policy_service import (
    RateLimiterRegistry,
    require_politeness_envelope,
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


# ---------------------------------------------------------------------------------
# Decision support (#908) — moved here from the admin's TypeScript.
#
# The copy is carried over verbatim from
# `platform-control/admin/src/resources/runs/run-decision-support.ts` rather than
# rewritten. This change is about WHERE the judgement lives; rewriting the wording in
# the same commit would make "the admin renders exactly what it rendered before"
# impossible to check from the diff.
#
# Every answer carries a CODE as well as its sentence. An agent branches on the code;
# a person reads the text. Prose alone would force a consumer to pattern-match English
# that a later PR may reword — which is the defect this issue names in run refusals.
# ---------------------------------------------------------------------------------

# The refusal each guard exception represents. A dict rather than a chain of
# `isinstance` checks so that adding an exception to the `except` clause without
# giving it a code fails with a KeyError here, loudly, instead of silently writing a
# refusal an agent cannot classify.
_REFUSAL_CODES: dict[type[Exception], RunRefusalCode] = {
    BlueprintTemplateNotEnabledError: RunRefusalCode.BLUEPRINT_TEMPLATE_NOT_ENABLED,
    CompliancePolicyMissingError: RunRefusalCode.COMPLIANCE_POLICY_MISSING,
    ProviderNotLiveReadyError: RunRefusalCode.PROVIDER_NOT_LIVE_READY,
}

_TERMINAL_FAILURE_RUN_STATUSES: frozenset[RunStatus] = frozenset(
    {RunStatus.FAILED, RunStatus.CANCELLED}
)

#: The pipeline rollup for a run that ended and whose downstream never finished.
#:
#: A fourth outcome beside `ok`/`blocked`/`failed`/`in_progress`, because none of
#: those is true of it. `in_progress` claims motion that stopped; `ok` is a false
#: green over documents that never became searchable; `blocked` would say a stage
#: reported blocked when none did, leaving `overall_status="blocked"` beside an
#: empty `blocked_stages`.
#:
#: This is the CLI's own word for the condition — `diagnose_stall` already names
#: `projection_stalled` and `publish_path_disabled` on exactly these runs
#: (`tools/evidara-cli/src/evidara_cli/coverage.py:332-356`), so the server said
#: "still moving" about a run the CLI had already diagnosed as stuck (#951).
OVERALL_STATUS_STALLED = "stalled"

#: How long after a run ends its downstream stages may still legitimately land.
#:
#: Acquisition completing is not the pipeline completing: platform-control marks a
#: run `completed` when the provider is done, and DI, projection and search follow
#: over NATS afterwards. So a terminal run with unfinished stages is normal for a
#: while and stuck after that, and only elapsed time tells the two apart — the
#: distinction `STALL_TOO_EARLY` describes but the CLI's snapshot cannot make.
#:
#: Measured against production on 2026-09-19 rather than guessed, because a floor
#: tuned to one sample withholds the truth on the next (AGENTS.md). Across the 24
#: runs that did project, the lag from `completed_at` to the last
#: `document_lifecycle_events` row was under 90s for 22 of them, 49min for one, and
#: **5h58m** for the largest (938 lifecycle events). The five genuinely stalled runs
#: are 68-74 days old. A 24h window clears the slowest real run by 4x and the
#: stalled ones miss it by 68x, so nothing sits near the boundary.
_PIPELINE_STALL_GRACE = timedelta(hours=24)


def _label(value: str) -> str:
    return value.replace("_", " ")


_WHY_IT_MATTERS: dict[RunMode, RunDecisionNote] = {
    RunMode.PRODUCTION: RunDecisionNote(
        code="production_run",
        text=(
            "This production run determines whether the source version can safely flow "
            "into the live operator surface."
        ),
    ),
    RunMode.ACCEPTANCE: RunDecisionNote(
        code="acceptance_run",
        text=(
            "This acceptance run reaches the live source to produce ADR-0030 evidence. "
            "A pass is the justification for enabling the template - it does not by "
            "itself turn either key."
        ),
    ),
    RunMode.PREVIEW: RunDecisionNote(
        code="preview_run",
        text=(
            "This preview run is the gate before promotion, so the result tells "
            "operators whether the version is ready."
        ),
    ),
}

_OVERALL_SUMMARY: dict[str, RunDecisionNote] = {
    "ok": RunDecisionNote(code="stages_healthy", text="Pipeline stages are healthy."),
    "blocked": RunDecisionNote(
        code="needs_remediation",
        text="One or more stages need remediation before the run can progress.",
    ),
    "failed": RunDecisionNote(
        code="downstream_failed",
        text="A downstream stage failed and needs operator attention.",
    ),
    OVERALL_STATUS_STALLED: RunDecisionNote(
        code="pipeline_stalled_after_run_end",
        text=(
            "The run itself finished, but the pipeline stopped short: downstream stages "
            "never reported and no further work is scheduled for them."
        ),
    ),
}
_OVERALL_SUMMARY_FALLBACK = RunDecisionNote(
    code="still_moving",
    text="At least one stage is still moving through the pipeline.",
)

_IF_IGNORED: dict[str, RunDecisionNote] = {
    "ok": RunDecisionNote(
        code="nothing_urgent",
        text=(
            "Nothing urgent happens; the run remains a completed audit trail unless "
            "someone investigates it later."
        ),
    ),
    "blocked": RunDecisionNote(
        code="stays_blocked",
        text="The run stays blocked until the relevant stage is remediated.",
    ),
    "failed": RunDecisionNote(
        code="failure_unresolved",
        text=("The failure remains unresolved and downstream progress will not clear itself."),
    ),
    OVERALL_STATUS_STALLED: RunDecisionNote(
        code="stall_will_not_clear",
        text=(
            "Nothing clears this on its own - the run has already ended, so the stages "
            "that never reported will not report later. Diagnose the stall and relaunch."
        ),
    ),
}

# Per-stage remediation. Keyed on the stage name, with the two status-driven answers
# handled first — an `ok` or dead stage needs nothing regardless of which stage it is.
_STAGE_ACTIONS: dict[str, tuple[str, str]] = {
    "acquisition": (
        "inspect_provider_jobs",
        "Check provider jobs for dispatch/crawl status and retry or cancel when stuck.",
    ),
    "document_intelligence": (
        "inspect_di_processing",
        "Inspect DI processing status events and error summaries for remediation.",
    ),
    "projection": (
        "confirm_lifecycle_events",
        "Confirm document lifecycle events are being emitted for this run.",
    ),
}
_STAGE_ACTION_FALLBACK = (
    "verify_search_visibility",
    "Verify lifecycle search disposition and confirm indexed document visibility in legal-search.",
)


def _stage_action(stage: RunPipelineHealthStage) -> RunStageAction:
    if stage.status is PipelineStageStatus.OK:
        code, text = "none_required", "No action required."
    elif stage.status is PipelineStageStatus.NOT_APPLICABLE:
        code, text = (
            "stage_will_not_run",
            "No action - this stage will not run for this run.",
        )
    else:
        code, text = _STAGE_ACTIONS.get(stage.stage, _STAGE_ACTION_FALLBACK)
    return RunStageAction(stage=stage.stage, status=stage.status, code=code, text=text)


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
        refusal_code: RunRefusalCode,
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
                # The code, beside the prose (#908). `failure_reason` keeps the
                # exception's own message — the part that says WHICH template or
                # policy — and this says what kind of refusal it was, so an agent
                # branches on a value instead of pattern-matching a sentence that a
                # later PR may reword. Matches the shape the ADR-0030 enablement
                # guard already returns as `refusals[].code` (#854).
                "refusal_code": refusal_code.value,
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
                    **self._publication_read_model(
                        row._mapping["run_metadata"],
                        row._mapping["artifacts_count"],
                    ),
                    "refused": (row._mapping["run_metadata"] or {}).get("refused") is True,
                    "refusal_code": (row._mapping["run_metadata"] or {}).get("refusal_code"),
                }
            )
            for row in rows
        ]
        return data, total

    @staticmethod
    def _publication_read_model(
        run_metadata: dict[str, Any] | None, artifacts_count: int
    ) -> dict[str, Any]:
        """Captured vs published, for a row read as columns rather than as a `Run`.

        `list_runs` selects columns, not entities, so it cannot reach
        `Run.published_artifacts_count` / `Run.publication_withheld`. It calls the same
        module-level helpers those properties call, so the list and the detail view
        cannot disagree about whether a run's documents were published.
        """
        return {
            "published_artifacts_count": published_artifacts_count_from(
                run_metadata, artifacts_count
            ),
            "publication_withheld": publication_withheld_from(run_metadata),
        }

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
        # The politeness envelope is the third thing that must hold before a
        # request leaves this process, and it refuses in the same shape: a
        # jurisdiction with no CompliancePolicy cannot dispatch, and the attempt
        # is recorded rather than discarded. Checked here as well as in
        # `_dispatch_run` for the same reason the two-key lock is — the
        # worker-backed path would otherwise accept the run and only refuse it
        # out-of-band, stranding a PENDING run no worker can ever dispatch.
        provider = self._resolve_provider_for_source_version(source_version)
        if provider is not None:
            try:
                await self._require_launchable(source_version, provider, request.mode)
                if source_version.execution_mode is not ExecutionMode.SHADOW:
                    await require_politeness_envelope(
                        self.session, source, self.rate_limiter_registry, self.robots_checker
                    )
            except (
                BlueprintTemplateNotEnabledError,
                CompliancePolicyMissingError,
                ProviderNotLiveReadyError,
            ) as exc:
                await self._record_refused_run(
                    source, source_version, request, str(exc), _REFUSAL_CODES[type(exc)]
                )
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
        # Applied HERE, not in a client. A run that ended `failed`/`cancelled` never
        # advances, so the stages it never reached are dead, not queued — and
        # reporting them as `pending` made a dead run look like it needed watching.
        # The admin had been re-labelling them in the browser since #649, which meant
        # the CLI, alerting and any agent still got the misleading answer (#908).
        stages = self._project_unreachable_stages(stages, run.status)
        # The run, not just its stages: a terminal run whose downstream never landed
        # must not keep reporting that the pipeline is advancing (#951). The stages
        # themselves are left alone on purpose - the CLI's `diagnose_stall` keys
        # `projection_stalled` off `projection.status in {pending, in_progress}`
        # (`coverage.py:340-351`), so re-labelling them here would silence the one
        # surface that already names this correctly.
        overall_status = self._resolve_overall_pipeline_status(stages, run)

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
            decision_support=self._build_decision_support(
                run=run,
                stages=stages,
                overall_status=overall_status,
                processing_status_event_count=len(processing_updates),
                document_lifecycle_event_count=len(lifecycle_events),
            ),
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
        elif latest_processing.status.value == "quarantined":
            # A refusal, not a success and not a failure (ADR-0047, #731). It must
            # not fall through to the `ok` branch below: a document the corpus
            # deliberately does not hold, reported as fine, is the false green this
            # repo keeps getting caught by. `blocked` is the honest word — the run
            # stopped here and no replay will move it.
            status = "blocked"
            detail = (
                latest_processing.error_summary
                or "Document-intelligence quarantined this manifestation: its text is not law."
            )
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
        if latest_processing.status.value == "quarantined":
            # Quarantine publishes nothing, so no lifecycle event is ever coming
            # (#841). Reporting `in_progress` here would leave the operator
            # watching a stage that has already finished refusing.
            return RunPipelineHealthStage(
                stage="projection",
                status="blocked",
                detail=(
                    "Projection blocked because DI quarantined this manifestation; "
                    "nothing was published."
                ),
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
    def _project_unreachable_stages(
        stages: list[RunPipelineHealthStage], run_status: RunStatus
    ) -> list[RunPipelineHealthStage]:
        """Re-label the stages a terminally-ended run will never reach.

        Only `pending` stages are touched, and only for `failed`/`cancelled` runs. A
        run still progressing legitimately has pending stages, and a completed run
        legitimately reports every stage `ok`.
        """
        if run_status not in _TERMINAL_FAILURE_RUN_STATUSES:
            return stages
        detail = (
            "Not applicable — the run was cancelled before this stage could start."
            if run_status is RunStatus.CANCELLED
            else "Not applicable — the run failed before this stage could start."
        )
        return [
            stage.model_copy(
                update={"status": PipelineStageStatus.NOT_APPLICABLE, "detail": detail}
            )
            if stage.status is PipelineStageStatus.PENDING
            else stage
            for stage in stages
        ]

    @staticmethod
    def _build_decision_support(
        *,
        run: Run,
        stages: list[RunPipelineHealthStage],
        overall_status: str,
        processing_status_event_count: int,
        document_lifecycle_event_count: int,
    ) -> RunDecisionSupport:
        """Answer the four operator questions, with a code beside every sentence.

        Moved from `platform-control/admin/src/resources/runs/run-decision-support.ts`
        (#908). The wording is carried over deliberately rather than rewritten: this
        change is about WHERE the judgement lives, and a rewrite would make "the admin
        renders the same thing" impossible to verify from the diff.
        """
        blocked = [
            s.stage
            for s in stages
            if s.status in (PipelineStageStatus.BLOCKED, PipelineStageStatus.FAILED)
        ]
        never_running = [s.stage for s in stages if s.status is PipelineStageStatus.NOT_APPLICABLE]
        # Three modes, not two. The ternary this replaces called an acceptance run
        # "this preview run" — the mislabelling #743 fixed at the badge sites.
        why = _WHY_IT_MATTERS[run.mode]

        if overall_status == "ok":
            blocked_note = RunDecisionNote(
                code="no_stage_blocked", text="No stage is blocked right now."
            )
        elif blocked:
            blocked_note = RunDecisionNote(
                code="stages_blocked",
                text=f"Blocked stages: {', '.join(_label(s) for s in blocked)}.",
            )
        elif overall_status == OVERALL_STATUS_STALLED:
            # Same shape as `moving_no_block` - no stage reported blocked - but the
            # opposite reading. Saying "still moving ... may need attention soon"
            # about a run that ended is the sentence #951 opened on.
            stalled_stages = [
                s.stage
                for s in stages
                if s.status in (PipelineStageStatus.PENDING, PipelineStageStatus.IN_PROGRESS)
            ]
            blocked_note = RunDecisionNote(
                code="stalled_no_block",
                text=(
                    "No stage reported blocked; these simply stopped reporting and the "
                    f"run has already ended: {', '.join(_label(s) for s in stalled_stages)}."
                ),
            )
        else:
            blocked_note = RunDecisionNote(
                code="moving_no_block",
                text=(
                    "No stage is blocked, but the pipeline is still moving and may need "
                    "operator attention soon."
                ),
            )
        if never_running:
            blocked_note = RunDecisionNote(
                code=blocked_note.code,
                text=(
                    f"{blocked_note.text} Downstream stages that will never run: "
                    f"{', '.join(_label(s) for s in never_running)}."
                ),
            )

        dated = [s for s in stages if s.updated_at is not None]
        if dated:
            latest = max(dated, key=lambda s: s.updated_at)  # type: ignore[arg-type,return-value]
            changed = RunDecisionNote(
                code="latest_stage_update",
                text=(
                    f"Most recent stage update: {_label(latest.stage)} is "
                    f"{_label(latest.status.value)}."
                ),
            )
        else:
            changed = RunDecisionNote(
                code="no_stage_updates",
                text=(
                    f"Health snapshot recorded {processing_status_event_count} processing "
                    f"events and {document_lifecycle_event_count} lifecycle events."
                ),
            )

        if run.status in _TERMINAL_FAILURE_RUN_STATUSES:
            ignored = RunDecisionNote(
                code="terminal_needs_relaunch",
                text=(
                    f"The run already ended as {run.status.value}; the stages it never "
                    "reached will not start on their own, so remediate and relaunch to "
                    "make progress."
                ),
            )
        else:
            ignored = _IF_IGNORED.get(
                overall_status,
                RunDecisionNote(
                    code="continues_advancing",
                    text=(
                        "The pipeline continues to advance and may still require "
                        "intervention if a later stage stops."
                    ),
                ),
            )

        return RunDecisionSupport(
            overall_summary=_OVERALL_SUMMARY.get(overall_status, _OVERALL_SUMMARY_FALLBACK),
            why_it_matters=why,
            what_is_blocked=blocked_note,
            what_changed_recently=changed,
            what_happens_if_ignored=ignored,
            blocked_stages=blocked,
            never_running_stages=never_running,
            next_actions=[_stage_action(stage) for stage in stages],
        )

    @staticmethod
    def _resolve_overall_pipeline_status(
        stages: list[RunPipelineHealthStage],
        run: Run | None = None,
        now: datetime | None = None,
    ) -> str:
        """Roll the stages up, and refuse to call a finished run's pipeline "moving".

        The stage rollup alone cannot say that: every stage after acquisition is
        `pending` on a run whose downstream never started, which is indistinguishable
        from a run whose downstream has not started *yet*. That is #951 — a
        `completed` run reporting `overall_status: in_progress` beside a panel saying
        "no more work is scheduled", forever, because nothing ever re-reads it.

        `run` is optional so the rollup stays callable on stages alone, but
        `get_pipeline_health` always passes it: without the run there is no
        `completed_at` and no terminality, so the stall can only be missed.
        """
        if any(stage.status == "failed" for stage in stages):
            return "failed"
        if any(stage.status == "blocked" for stage in stages):
            return "blocked"
        if any(stage.status in {"pending", "in_progress"} for stage in stages):
            if RunService._pipeline_has_stalled(run, now=now):
                return OVERALL_STATUS_STALLED
            return "in_progress"
        return "ok"

    @staticmethod
    def _pipeline_has_stalled(run: Run | None, *, now: datetime | None = None) -> bool:
        """True when a run has ended and its unfinished stages are out of time.

        Deliberately scoped to `COMPLETED`. A `failed`/`cancelled` run already has its
        unreached stages re-labelled `not_applicable` by `_project_unreachable_stages`
        and its acquisition stage carries `failed`/`blocked`, so the rollup answers
        those before reaching here - and *those* stages are dead by design, where
        these were supposed to run and did not.

        Returns False when `completed_at` is missing rather than assuming a stall:
        an unknown age is not an old one (ADR-0052).
        """
        if run is None or run.status is not RunStatus.COMPLETED:
            return False
        completed_at = run.completed_at
        if completed_at is None:
            return False
        if completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=UTC)
        return (now or datetime.now(UTC)) - completed_at >= _PIPELINE_STALL_GRACE

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
        #
        # A missing policy REFUSES the dispatch (slug `compliance_policy_missing`)
        # rather than resolving to None and letting `limited_get` fall through to
        # an unpaced, robots-blind `client.get`. SHADOW is exempt for the same
        # reason `_require_launchable` exempts it — cassettes, no portal.
        if source_version.execution_mode is ExecutionMode.SHADOW:
            envelope = None
        else:
            envelope = await require_politeness_envelope(
                self.session, source, self.rate_limiter_registry, self.robots_checker
            )
        limiter_token = current_rate_limiter.set(envelope.limiter if envelope else None)
        robots_token = current_robots_context.set(envelope.robots if envelope else None)
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
        upstream_locator = resolve_upstream_locator(artifacts[0].artifact_metadata)

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
            upstream_locator = resolve_upstream_locator(artifact.artifact_metadata)

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
        """Hand the dispatched run's events to the broker, honestly (#707, #853).

        The first thing this does is read `run.status`: a FAILED run publishes
        nothing (#853). See `_withhold_dispatch_publication`, which also records the
        rollback decision — the artifacts stay, only the events are dropped.

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
            run = await self.session.get(Run, pending.run_id) if pending.run_id else None
            if run is None or run.status is RunStatus.FAILED:
                # A FAILED run does not get to hand its documents downstream (#853).
                # See `_withhold_dispatch_publication` for why this lives here and not
                # in the providers.
                await self._withhold_dispatch_publication(run, pending)
                continue
            run_failures: list[str] = []
            published_artifacts = 0
            for artifact_id in pending.raw_artifact_ids:
                artifact = await self.session.get(RawArtifact, artifact_id)
                if artifact is None:  # pragma: no cover - defensive guard
                    continue
                try:
                    await self.publisher.publish_raw_artifact_available(artifact)
                except Exception as exc:
                    run_failures.append(f"raw_artifact.available for {artifact_id}: {exc}")
                    continue
                published_artifacts += 1
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
                await self._record_dispatch_publish_failure(
                    pending.run_id, run_failures, published_artifacts
                )
                failures.extend(run_failures)
        return failures

    async def _withhold_dispatch_publication(
        self, run: Run | None, pending: PendingDispatchPublications
    ) -> None:
        """Drop a failed dispatch's events instead of publishing them (#853).

        `_dispatch_run` persists `inline_resources` and builds the bundle events
        BEFORE it reads `inline_failure_reason` (:1348-1374 / :1376-1381). A provider
        that returns documents *and* a reason not to trust them therefore left the run
        red while its artifacts went downstream anyway — the corpus would be worse for
        having run the check than for skipping it.

        This never bit because every provider gated its failure reason on
        `if not resources` (`deterministic_http:143`, `fedlex_sparql:328`,
        `eur_lex:284`, `ris_ogd:239`, `legifrance:155`, `ch_court_decisions:336`,
        `portal_http_provider_base:162`, `gemeinde:426`) — an unstated invariant
        `_dispatch_run` was written on. #845 was the first provider to want the other
        combination and had to discard the batch itself. That fix is correct and stays,
        but it only covers one provider; the invariant belongs at the boundary that
        actually publishes, where no future provider can miss it.

        **The persisted rows are deliberately NOT rolled back.** `RawArtifact` and
        `CapturedResource` are the evidence of what the source served — for #845 the
        diverged bytes are the whole finding — and nothing downstream reads them
        without an event, because document-intelligence is a NATS consumer. Deleting
        them would also erase `artifacts_count`, collapsing "captured 12, published 0"
        into an empty run and hiding exactly the discard an operator needs to see.
        Withholding is a publication decision, not a storage one.

        `failure_reason` is left alone on purpose: the provider's reason is why the run
        failed, and overwriting it with "events withheld" would replace the cause with
        its consequence. The marker in `run_metadata` carries the consequence.
        """
        withheld = len(pending.raw_artifact_ids)
        logging.getLogger(__name__).warning(
            "withheld %d raw_artifact.available and %d artifact_bundle.available event(s) "
            "for run %s: the run is %s, so its captured documents are not published",
            withheld,
            len(pending.bundle_events),
            pending.run_id,
            "unresolvable" if run is None else run.status.value,
        )
        if run is None:  # pragma: no cover - defensive guard
            return
        run.run_metadata = {
            **(run.run_metadata or {}),
            DISPATCH_PUBLISH_WITHHELD_KEY: True,
            PUBLISHED_ARTIFACTS_COUNT_KEY: 0,
        }
        await self.session.commit()

    async def _record_dispatch_publish_failure(
        self, run_id: str | None, run_failures: list[str], published_artifacts: int = 0
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
        run.run_metadata = {
            **(run.run_metadata or {}),
            "dispatch_publish_failed": True,
            # What really left the service, not what was captured (#853). A partial
            # handoff is neither 0 nor `artifacts_count`.
            PUBLISHED_ARTIFACTS_COUNT_KEY: published_artifacts,
        }
        await self.session.commit()

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
