from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy import select

from platform_control.domain import ProviderJobStatus, RunMode, RunStatus
from platform_control.errors import InvalidStateTransitionError
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.captured_resource import CapturedResource
from platform_control.models.provider_job import ProviderJob
from platform_control.models.raw_artifact import RawArtifact
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
async def test_create_run_persists_explicit_scope_and_replay_metadata(session) -> None:
    source, version, source_service = await _seed_source_version(session)
    await source_service.approve_source_version(version.source_version_id)
    run_service = RunService(session, StubProvider())

    run = await run_service.create_run(
        CreateRunRequest(
            source_id=source.source_id,
            source_version_id=version.source_version_id,
            mode=RunMode.PRODUCTION,
            scope={
                "kind": "time_window",
                "since": "2026-01-01T00:00:00Z",
                "until": "2026-01-31T23:59:59Z",
                "max_resources": 250,
            },
            replay={
                "mode": "backfill",
                "reason": "Fill January gap after provider outage",
            },
        )
    )

    assert run.run_metadata["scope"]["kind"] == "time_window"
    assert run.run_metadata["scope"]["max_resources"] == 250
    assert run.run_metadata["replay"]["mode"] == "backfill"
    assert run.run_metadata["replay"]["reason"] == "Fill January gap after provider outage"


def test_partial_rerun_requires_parent_run_id() -> None:
    with pytest.raises(ValueError):
        CreateRunRequest(
            source_id="src_123",
            source_version_id="sv_123",
            replay={"mode": "partial_rerun"},
        )


async def test_list_runs_supports_filters_and_joined_display_fields(session) -> None:
    source, version, source_service = await _seed_source_version(session)

    preview_run = await RunService(
        session,
        StubProvider(external_job_id="crawl_job_preview"),
    ).create_run(
        CreateRunRequest(
            source_id=source.source_id,
            source_version_id=version.source_version_id,
            mode=RunMode.PREVIEW,
        )
    )

    await source_service.approve_source_version(version.source_version_id)
    production_run = await RunService(
        session,
        StubProvider(external_job_id="crawl_job_production"),
    ).create_run(
        CreateRunRequest(
            source_id=source.source_id,
            source_version_id=version.source_version_id,
            mode=RunMode.PRODUCTION,
        )
    )
    preview_run.status = RunStatus.COMPLETED
    await session.commit()

    run_service = RunService(session)
    all_runs = await run_service.list_runs()
    production_only = await run_service.list_runs(mode=RunMode.PRODUCTION)
    completed_only = await run_service.list_runs(status=RunStatus.COMPLETED)

    assert [run.run_id for run in all_runs] == [production_run.run_id, preview_run.run_id]
    assert all_runs[0].source_name == "Zurich decisions"
    assert all_runs[0].version_label == "v1"
    assert [run.run_id for run in production_only] == [production_run.run_id]
    assert [run.run_id for run in completed_only] == [preview_run.run_id]


@pytest.mark.asyncio
async def test_run_detail_lists_expose_resources_artifacts_and_provider_jobs(session) -> None:
    source, version, source_service = await _seed_source_version(session)
    await source_service.approve_source_version(version.source_version_id)
    run = await RunService(session, StubProvider(external_job_id="crawl_job_detail")).create_run(
        CreateRunRequest(
            source_id=source.source_id,
            source_version_id=version.source_version_id,
            mode=RunMode.PREVIEW,
        )
    )

    session.add_all(
        [
            RawArtifact(
                artifact_id="art_detail_1",
                run_id=run.run_id,
                source_id=source.source_id,
                source_version_id=version.source_version_id,
                storage_path="gs://bucket/runs/run_detail/art_detail_1.json",
                content_type="text/html",
                artifact_metadata={"pageTitle": "Decision"},
            ),
            CapturedResource(
                captured_resource_id="cap_detail_1",
                artifact_id="art_detail_1",
                run_id=run.run_id,
                source_id=source.source_id,
                source_version_id=version.source_version_id,
                provider_job_id=None,
                source_url="https://example.com/detail",
                final_url="https://example.com/detail",
                title="Decision detail",
                content_type="text/html",
                checksum="checksum_detail_1",
                http_status=200,
                discovery_depth=1,
            ),
        ]
    )
    provider_job = await session.scalar(select(ProviderJob).where(ProviderJob.run_id == run.run_id))
    assert provider_job is not None
    provider_job.status = ProviderJobStatus.COMPLETED
    provider_job.last_event_type = "crawl.completed"
    run.artifacts_count = 1
    run.captured_resources_count = 1
    await session.commit()

    run_service = RunService(session)
    captured_resources = await run_service.list_captured_resources(run.run_id)
    raw_artifacts = await run_service.list_raw_artifacts(run.run_id)
    provider_jobs = await run_service.list_provider_jobs(run.run_id)

    assert [resource.captured_resource_id for resource in captured_resources] == ["cap_detail_1"]
    assert captured_resources[0].title == "Decision detail"
    assert [artifact.artifact_id for artifact in raw_artifacts] == ["art_detail_1"]
    assert raw_artifacts[0].artifact_metadata == {"pageTitle": "Decision"}
    assert [job.provider_job_id for job in provider_jobs] == [provider_job.provider_job_id]
    assert provider_jobs[0].status is ProviderJobStatus.COMPLETED
    assert provider_jobs[0].last_event_type == "crawl.completed"


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
@pytest.mark.parametrize(
    "terminal_status",
    [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED],
)
async def test_cancel_run_rejects_terminal_status(session, terminal_status) -> None:
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
    run.status = terminal_status
    await session.commit()

    with pytest.raises(InvalidStateTransitionError):
        await run_service.cancel_run(run.run_id)


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


@pytest.mark.asyncio
async def test_create_run_worker_backend_keeps_run_pending(session) -> None:
    source, version, source_service = await _seed_source_version(session)
    await source_service.approve_source_version(version.source_version_id)
    run_service = RunService(session, StubProvider(), run_dispatch_backend="worker")

    run = await run_service.create_run(
        CreateRunRequest(
            source_id=source.source_id,
            source_version_id=version.source_version_id,
            mode=RunMode.PRODUCTION,
        )
    )
    provider_job = await session.scalar(select(ProviderJob).where(ProviderJob.run_id == run.run_id))

    assert run.status is RunStatus.PENDING
    assert provider_job is None


@pytest.mark.asyncio
async def test_dispatch_pending_runs_promotes_runs_to_running(session) -> None:
    source, version, source_service = await _seed_source_version(session)
    await source_service.approve_source_version(version.source_version_id)
    run_service = RunService(session, StubProvider(), run_dispatch_backend="worker")
    run = await run_service.create_run(
        CreateRunRequest(
            source_id=source.source_id,
            source_version_id=version.source_version_id,
            mode=RunMode.PREVIEW,
        )
    )

    dispatched = await run_service.dispatch_pending_runs()
    provider_job = await session.scalar(select(ProviderJob).where(ProviderJob.run_id == run.run_id))
    refreshed = await run_service.get_run(run.run_id)

    assert dispatched == 1
    assert refreshed.status is RunStatus.RUNNING
    assert provider_job is not None
