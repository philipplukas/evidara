from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy import select

from platform_control.domain import RunMode, RunStatus
from platform_control.errors import InvalidStateTransitionError
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.captured_resource import CapturedResource
from platform_control.models.provider_job import ProviderJob
from platform_control.schemas.run import CreateRunRequest
from platform_control.schemas.source import (
    CreateSourceRequest,
    CreateSourceVersionRequest,
    FirecrawlAcquisitionSpec,
)
from platform_control.services.firecrawl_provider import ProviderStartResult
from platform_control.services.run_service import RunService
from platform_control.services.source_service import SourceService


@dataclass
class StubProvider:
    external_job_id: str = "crawl_job_123"

    async def start_run(self, source, source_version, run) -> ProviderStartResult:
        del source, source_version, run
        return ProviderStartResult(
            external_job_id=self.external_job_id,
            request_payload={"url": "https://example.com"},
            response_payload={"id": self.external_job_id, "success": True},
        )


async def _seed_source_version(session):
    session.add(Jurisdiction(jurisdiction_id="jur_ch", name="Switzerland", slug="ch"))
    session.add(
        Authority(
            authority_id="auth_zh_admin",
            jurisdiction_id="jur_ch",
            name="Zurich Administrative Court",
            slug="zh-admin-court",
        )
    )
    await session.commit()

    source_service = SourceService(session)
    source = await source_service.create_source(
        CreateSourceRequest(
            name="Zurich decisions",
            jurisdiction_id="jur_ch",
            authority_id="auth_zh_admin",
        )
    )
    version = await source_service.create_source_version(
        source.source_id,
        CreateSourceVersionRequest(
            version_label="v1",
            acquisition_spec=FirecrawlAcquisitionSpec(seed_url="https://example.com/decisions"),
        ),
    )
    return source, version, source_service


@pytest.mark.asyncio
async def test_production_runs_require_approved_versions(session) -> None:
    source, version, _ = await _seed_source_version(session)
    run_service = RunService(session, StubProvider())

    with pytest.raises(InvalidStateTransitionError):
        await run_service.create_run(
            CreateRunRequest(
                source_id=source.source_id,
                source_version_id=version.source_version_id,
                mode=RunMode.PRODUCTION,
            )
        )


@pytest.mark.asyncio
async def test_create_run_persists_provider_job(session) -> None:
    source, version, source_service = await _seed_source_version(session)
    await source_service.approve_source_version(version.source_version_id)
    run_service = RunService(session, StubProvider())

    run = await run_service.create_run(
        CreateRunRequest(
            source_id=source.source_id,
            source_version_id=version.source_version_id,
            mode=RunMode.PRODUCTION,
        )
    )

    provider_job = await session.scalar(select(ProviderJob).where(ProviderJob.run_id == run.run_id))

    assert run.status is RunStatus.RUNNING
    assert provider_job is not None
    assert provider_job.external_job_id == "crawl_job_123"


@pytest.mark.asyncio
async def test_cancel_run_marks_it_cancelled(session) -> None:
    source, version, source_service = await _seed_source_version(session)
    await source_service.approve_source_version(version.source_version_id)
    run_service = RunService(session, StubProvider())
    run = await run_service.create_run(
        CreateRunRequest(
            source_id=source.source_id,
            source_version_id=version.source_version_id,
            mode=RunMode.PREVIEW,
        )
    )

    cancelled = await run_service.cancel_run(run.run_id)

    assert cancelled.status is RunStatus.CANCELLED
    assert cancelled.failure_reason == "Cancelled by operator."


@pytest.mark.asyncio
async def test_preview_summary_flags_decision_boilerplate_and_duplicate_resources(session) -> None:
    source, version, source_service = await _seed_source_version(session)
    await source_service.approve_source_version(version.source_version_id)
    run_service = RunService(session, StubProvider())
    run = await run_service.create_run(
        CreateRunRequest(
            source_id=source.source_id,
            source_version_id=version.source_version_id,
            mode=RunMode.PREVIEW,
        )
    )
    session.add_all(
        [
            CapturedResource(
                captured_resource_id="cap_1",
                artifact_id="art_1",
                run_id=run.run_id,
                source_id=source.source_id,
                source_version_id=version.source_version_id,
                provider_job_id=None,
                source_url="https://example.com/decisions/2026-1",
                final_url="https://example.com/decisions/2026-1",
                title="Decision 2026/1",
                content_type="text/html",
                checksum="dup_1",
                http_status=200,
            ),
            CapturedResource(
                captured_resource_id="cap_2",
                artifact_id="art_2",
                run_id=run.run_id,
                source_id=source.source_id,
                source_version_id=version.source_version_id,
                provider_job_id=None,
                source_url="https://example.com/privacy",
                final_url="https://example.com/privacy",
                title="Privacy policy",
                content_type="text/html",
                checksum="unique_2",
                http_status=200,
            ),
            CapturedResource(
                captured_resource_id="cap_3",
                artifact_id="art_3",
                run_id=run.run_id,
                source_id=source.source_id,
                source_version_id=version.source_version_id,
                provider_job_id=None,
                source_url="https://example.com/archive/file.pdf",
                final_url="https://example.com/archive/file.pdf",
                title="Decision PDF",
                content_type="application/pdf",
                checksum="dup_1",
                http_status=200,
            ),
        ]
    )
    run.artifacts_count = 3
    run.captured_resources_count = 3
    await session.commit()

    summary = await run_service.get_preview_summary(run.run_id)

    assert summary.captured_url_count == 3
    assert summary.pdf_count == 1
    assert summary.likely_decision_page_count == 2
    assert summary.likely_boilerplate_page_count == 1
    assert summary.likely_duplicate_page_count == 2
    assert summary.content_type_breakdown[0].count >= summary.content_type_breakdown[-1].count
