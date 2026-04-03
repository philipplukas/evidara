from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.domain import ProviderJobStatus, RunMode, RunStatus, SourceVersionStatus
from platform_control.errors import InvalidStateTransitionError, NotFoundError
from platform_control.models.captured_resource import CapturedResource
from platform_control.models.provider_job import ProviderJob
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.schemas.run import (
    CreateRunRequest,
    RunPreviewSummaryBreakdownEntry,
    RunPreviewSummaryDriftCheck,
    RunPreviewSummaryResponse,
    RunPreviewSummarySample,
)
from platform_control.services.firecrawl_provider import FirecrawlProvider


class RunService:
    _DECISION_PATTERN = re.compile(
        r"\b(decision|judg(?:e)?ment|order|case|ruling)\b",
        re.IGNORECASE,
    )
    _BOILERPLATE_PATTERN = re.compile(
        r"\b(privacy|terms|impressum|contact|about|help|faq|cookie|sitemap)\b",
        re.IGNORECASE,
    )

    def __init__(self, session: AsyncSession, provider: FirecrawlProvider) -> None:
        self.session = session
        self.provider = provider

    async def create_run(self, request: CreateRunRequest) -> Run:
        source = await self.session.get(Source, request.source_id)
        if source is None:
            raise NotFoundError(f"Source not found: {request.source_id}")

        source_version = await self.session.get(SourceVersion, request.source_version_id)
        if source_version is None:
            raise NotFoundError(f"Source version not found: {request.source_version_id}")
        if source_version.source_id != source.source_id:
            raise InvalidStateTransitionError(
                "Source version does not belong to the requested source."
            )

        self._validate_version_for_run_mode(source_version, request.mode)

        run = Run(
            source_id=source.source_id,
            source_version_id=source_version.source_version_id,
            mode=request.mode,
            status=RunStatus.PENDING,
        )
        self.session.add(run)
        await self.session.flush()

        provider_result = await self.provider.start_run(source, source_version, run)
        provider_job = ProviderJob(
            run_id=run.run_id,
            external_job_id=provider_result.external_job_id,
            status=ProviderJobStatus.ACCEPTED,
            request_payload=provider_result.request_payload,
            response_payload=provider_result.response_payload,
        )
        self.session.add(provider_job)

        run.status = RunStatus.RUNNING
        run.started_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def get_run(self, run_id: str) -> Run:
        run = await self.session.get(Run, run_id)
        if run is None:
            raise NotFoundError(f"Run not found: {run_id}")
        return run

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
