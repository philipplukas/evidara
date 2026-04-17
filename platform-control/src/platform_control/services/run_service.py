from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from acquisition_core.normalization import ArtifactPipeline
from platform_control.domain import ProviderJobStatus, RunMode, RunStatus, SourceVersionStatus
from platform_control.errors import (
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
from platform_control.models.document_lifecycle_event import DocumentLifecycleEvent
from platform_control.models.processing_status_update import ProcessingStatusUpdate
from platform_control.models.provider_job import ProviderJob
from platform_control.models.raw_artifact import RawArtifact
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
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
from platform_control.services.compliance_policy_service import (
    RateLimiterRegistry,
    resolve_rate_limiter_for_source,
    resolve_robots_context_for_source,
)
from platform_control.services.politeness import current_rate_limiter
from platform_control.services.provider_registry import ProviderRegistry
from platform_control.services.replay_checkpoint import checkpoint_dict_from_parent
from platform_control.services.robots import RobotsChecker, current_robots_context


@dataclass(slots=True)
class PendingDispatchPublications:
    raw_artifact_ids: list[str] = field(default_factory=list)
    bundle_events: list[dict[str, Any]] = field(default_factory=list)


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

        count_result = await self.session.execute(
            select(func.count()).select_from(base_query.subquery())
        )
        total = count_result.scalar() or 0

        rows = await self.session.execute(base_query.limit(limit).offset(offset))
        data = [RunListItemResponse.model_validate(dict(row._mapping)) for row in rows]
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
        await self._publish_pending_dispatch_events([pending_publications])
        return run

    async def get_run_readiness(
        self, *, source_id: str, source_version_id: str, mode: RunMode
    ) -> RunReadinessResponse:
        source = await self.session.get(Source, source_id)
        source_version = await self.session.get(SourceVersion, source_version_id)
        return self.assess_run_readiness(
            source=source,
            source_version=source_version,
            source_id=source_id,
            source_version_id=source_version_id,
            mode=mode,
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
        for run in pending_runs:
            source = await self.session.get(Source, run.source_id)
            source_version = await self.session.get(SourceVersion, run.source_version_id)
            if source is None or source_version is None:
                continue
            pending_publications.append(await self._dispatch_run(source, source_version, run))
            dispatched += 1

        if dispatched > 0:
            await self.session.commit()
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
                await self._publish_pending_dispatch_events([pending_publications])
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
            normalized_seed_url = seed_url.strip() if isinstance(seed_url, str) else ""
            normalized_seed_urls = (
                [url.strip() for url in seed_urls if isinstance(url, str) and url.strip()]
                if isinstance(seed_urls, list)
                else []
            )
            normalized_base_url = base_url.strip() if isinstance(base_url, str) else ""
            has_seed = bool(normalized_seed_url or normalized_seed_urls or normalized_base_url)
            seed_detail = (
                "Acquisition spec has at least one seed or base URL."
                if has_seed
                else "Acquisition spec must define seed_url, seed_urls, or base_url."
            )
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
        pending_publications = PendingDispatchPublications()

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
        return pending_publications

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

    async def _resolve_attribution(
        self, jurisdiction_id: str | None
    ) -> dict[str, Any] | None:
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
    ) -> None:
        for pending in pending_publications:
            for artifact_id in pending.raw_artifact_ids:
                artifact = await self.session.get(RawArtifact, artifact_id)
                if artifact is None:  # pragma: no cover - defensive guard
                    continue
                await self.publisher.publish_raw_artifact_available(artifact)
            for event in pending.bundle_events:
                await self.publisher.publish_artifact_bundle_available(event)

    @staticmethod
    def _upstream_locator(artifact_metadata: dict[str, Any]) -> str:
        return str(
            artifact_metadata.get("source_url")
            or artifact_metadata.get("final_url")
            or "https://unknown.local/resource"
        )

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
