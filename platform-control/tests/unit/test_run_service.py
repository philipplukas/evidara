from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy import select

from platform_control.domain import ProcessingStatus, ProviderJobStatus, RunMode, RunStatus
from platform_control.errors import InvalidStateTransitionError
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.captured_resource import CapturedResource
from platform_control.models.document_lifecycle_event import DocumentLifecycleEvent
from platform_control.models.processing_status_update import ProcessingStatusUpdate
from platform_control.models.provider_job import ProviderJob
from platform_control.models.raw_artifact import RawArtifact
from platform_control.schemas.run import CreateRunRequest
from platform_control.schemas.source import (
    CreateSourceRequest,
    CreateSourceVersionRequest,
    FirecrawlAcquisitionSpec,
)
from platform_control.services.acquisition_provider import ProviderResource, ProviderStartResult
from platform_control.services.provider_registry import ProviderRegistry
from platform_control.services.run_service import RunService
from platform_control.services.source_service import SourceService


@dataclass
class StubProvider:
    provider_name: str = "firecrawl"
    external_job_id: str | None = None
    calls: int = 0

    async def start_run(self, source, source_version, run) -> ProviderStartResult:
        del source, source_version
        self.calls += 1
        external_job_id = self.external_job_id or f"crawl_job_{run.run_id}_{self.calls}"
        return ProviderStartResult(
            provider=self.provider_name,
            external_job_id=external_job_id,
            request_payload={"url": "https://example.com"},
            response_payload={"id": external_job_id, "success": True},
        )


@dataclass
class FedlexSparqlProviderStub:
    provider_name: str = "fedlex_sparql"

    async def start_run(self, source, source_version, run) -> ProviderStartResult:
        del source, run
        work_uri = str(source_version.acquisition_spec["seed_url"])
        expression_uris = [
            "https://fedlex.data.admin.ch/eli/cc/1999/404/de",
            "https://fedlex.data.admin.ch/eli/cc/1999/404/fr",
        ]
        return ProviderStartResult(
            provider=self.provider_name,
            external_job_id="sparql_job_001",
            request_payload={
                "work_uri": work_uri,
                "sparql_endpoint": "https://fedlex.data.admin.ch/sparqlendpoint",
            },
            response_payload={
                "work_uri": work_uri,
                "expression_uris": expression_uris,
            },
        )


@dataclass
class InlineJsonDeterministicProvider:
    """Simulates deterministic_http capturing a single JSON document (no HTML)."""

    provider_name: str = "deterministic_http"

    async def start_run(self, source, source_version, run) -> ProviderStartResult:
        del source, source_version, run
        return ProviderStartResult(
            provider=self.provider_name,
            external_job_id="det_job_json",
            request_payload={"seed_urls": ["https://registry.npmjs.org/left-pad/latest"]},
            response_payload={"captured": 1},
            inline_resources=[
                ProviderResource(
                    source_url="https://registry.npmjs.org/left-pad/latest",
                    final_url="https://registry.npmjs.org/left-pad/latest",
                    content_type="application/json",
                    body='{"name":"left-pad","version":"1.3.0"}',
                    title=None,
                    http_status=200,
                    discovery_depth=0,
                )
            ],
        )


@dataclass
class InlineDeterministicProvider:
    provider_name: str = "deterministic_http"

    async def start_run(self, source, source_version, run) -> ProviderStartResult:
        del source, source_version, run
        return ProviderStartResult(
            provider=self.provider_name,
            external_job_id="det_job_123",
            request_payload={"seed_urls": ["https://example.com/decisions/2026-01"]},
            response_payload={"captured": 1},
            inline_resources=[
                ProviderResource(
                    source_url="https://example.com/decisions/2026-01?utm_source=test",
                    final_url="https://example.com/decisions/2026-01?utm_source=test",
                    content_type="text/html",
                    body="<html><title>Decision 2026/01</title><body>Hello</body></html>",
                    title="Decision 2026/01",
                    http_status=200,
                    discovery_depth=0,
                )
            ],
        )


@dataclass
class FlakyInlineDeterministicProvider:
    provider_name: str = "deterministic_http"
    calls: int = 0

    async def start_run(self, source, source_version, run) -> ProviderStartResult:
        del source, source_version, run
        self.calls += 1
        if self.calls >= 2:
            raise RuntimeError("simulated provider failure after first inline run")
        return ProviderStartResult(
            provider=self.provider_name,
            external_job_id="det_job_flaky_1",
            request_payload={"seed_urls": ["https://example.com/decisions/2026-01"]},
            response_payload={"captured": 1},
            inline_resources=[
                ProviderResource(
                    source_url="https://example.com/decisions/2026-01?utm_source=test",
                    final_url="https://example.com/decisions/2026-01?utm_source=test",
                    content_type="text/html",
                    body="<html><title>Decision 2026/01</title><body>Hello</body></html>",
                    title="Decision 2026/01",
                    http_status=200,
                    discovery_depth=0,
                )
            ],
        )


@dataclass
class InMemoryArtifactStore:
    stored_pages: dict[str, dict] | None = None
    stored_manifests: dict[str, dict] | None = None

    def __post_init__(self) -> None:
        if self.stored_pages is None:
            self.stored_pages = {}
        if self.stored_manifests is None:
            self.stored_manifests = {}

    async def store_page_payload(self, run_id: str, artifact_id: str, payload: dict) -> str:
        assert self.stored_pages is not None
        self.stored_pages[artifact_id] = payload
        return f"gs://test-artifacts/{run_id}/{artifact_id}.json"

    async def store_bundle_manifest(
        self,
        run_id: str,
        bundle_manifest_id: str,
        payload: dict,
    ) -> dict:
        assert self.stored_manifests is not None
        self.stored_manifests[bundle_manifest_id] = payload
        return {
            "uri": f"gs://test-manifests/{run_id}/{bundle_manifest_id}.json",
            "content_type": "application/json",
            "byte_size": 1,
            "checksum": "a" * 64,
            "checksum_algorithm": "sha256",
        }


@dataclass
class RecordingPublisher:
    raw_artifact_ids: list[str] | None = None
    bundle_events: list[dict] | None = None

    def __post_init__(self) -> None:
        if self.raw_artifact_ids is None:
            self.raw_artifact_ids = []
        if self.bundle_events is None:
            self.bundle_events = []

    async def publish_raw_artifact_available(self, artifact: RawArtifact) -> None:
        assert self.raw_artifact_ids is not None
        self.raw_artifact_ids.append(artifact.artifact_id)

    async def publish_artifact_bundle_available(self, event: dict) -> None:
        assert self.bundle_events is not None
        self.bundle_events.append(event)


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
async def test_get_run_readiness_reports_pass_for_valid_configuration(session) -> None:
    source, version, source_service = await _seed_source_version(session)
    await source_service.approve_source_version(version.source_version_id)
    run_service = RunService(session, StubProvider())

    readiness = await run_service.get_run_readiness(
        source_id=source.source_id,
        source_version_id=version.source_version_id,
        mode=RunMode.PRODUCTION,
    )

    assert readiness.ready is True
    assert all(check.ok for check in readiness.checks)


@pytest.mark.asyncio
async def test_overlay_template_source_version_passes_readiness_checks(session) -> None:
    session.add(Jurisdiction(jurisdiction_id="jur_at", name="Austria", slug="at"))
    session.add(
        Authority(
            authority_id="auth_at_ris",
            jurisdiction_id="jur_at",
            name="RIS",
            slug="ris",
        )
    )
    await session.commit()

    source_service = SourceService(session)
    source = await source_service.create_source(
        CreateSourceRequest(
            name="AT RIS decisions",
            jurisdiction_id="jur_at",
            authority_id="auth_at_ris",
        )
    )
    version = await source_service.create_source_version(
        source.source_id,
        CreateSourceVersionRequest(
            version_label="at-template-v1",
            overlay_id="at",
            provider_template_id="ris_ogd_bundesrecht",
        ),
    )
    await source_service.approve_source_version(version.source_version_id)

    run_service = RunService(session, StubProvider())
    readiness = await run_service.get_run_readiness(
        source_id=source.source_id,
        source_version_id=version.source_version_id,
        mode=RunMode.PRODUCTION,
    )

    assert readiness.ready is True
    assert all(check.ok for check in readiness.checks)


@pytest.mark.asyncio
async def test_create_run_fails_preflight_when_seed_urls_are_missing(session) -> None:
    source, version, source_service = await _seed_source_version(session)
    await source_service.approve_source_version(version.source_version_id)
    version.acquisition_spec = {"mode": "crawl"}
    await session.commit()
    run_service = RunService(session, StubProvider())

    with pytest.raises(InvalidStateTransitionError, match="Acquisition spec must define seed_url"):
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
    assert provider_job.external_job_id == f"crawl_job_{run.run_id}_1"


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


@pytest.mark.asyncio
async def test_create_run_copies_parent_replay_checkpoint(session) -> None:
    source, version, source_service = await _seed_source_version(session)
    await source_service.approve_source_version(version.source_version_id)
    run_service = RunService(session, StubProvider())
    parent = await run_service.create_run(
        CreateRunRequest(
            source_id=source.source_id,
            source_version_id=version.source_version_id,
            mode=RunMode.PRODUCTION,
        )
    )
    md = dict(parent.run_metadata or {})
    md["replay_checkpoint"] = {"schema_version": 1, "pages_ingested": 7}
    parent.run_metadata = md
    await session.commit()

    child = await run_service.create_run(
        CreateRunRequest(
            source_id=source.source_id,
            source_version_id=version.source_version_id,
            mode=RunMode.PRODUCTION,
            replay={"mode": "partial_rerun", "parent_run_id": parent.run_id},
        )
    )

    assert child.run_metadata["replay_checkpoint"]["pages_ingested"] == 7


def test_partial_rerun_requires_parent_run_id() -> None:
    with pytest.raises(ValueError):
        CreateRunRequest(
            source_id="src_123",
            source_version_id="sv_123",
            replay={"mode": "partial_rerun"},
        )


@pytest.mark.asyncio
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
    all_runs, all_total = await run_service.list_runs()
    production_only, production_total = await run_service.list_runs(mode=RunMode.PRODUCTION)
    completed_only, completed_total = await run_service.list_runs(status=RunStatus.COMPLETED)

    assert [run.run_id for run in all_runs] == [production_run.run_id, preview_run.run_id]
    assert all_total == 2
    assert all_runs[0].source_name == "Zurich decisions"
    assert all_runs[0].version_label == "v1"
    assert [run.run_id for run in production_only] == [production_run.run_id]
    assert production_total == 1
    assert [run.run_id for run in completed_only] == [preview_run.run_id]
    assert completed_total == 1


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

    cap_ids = [r.captured_resource_id for r in captured_resources.data]
    assert cap_ids == ["cap_detail_1"]
    assert captured_resources.data[0].title == "Decision detail"
    assert captured_resources.total == 1
    assert [artifact.artifact_id for artifact in raw_artifacts.data] == ["art_detail_1"]
    assert raw_artifacts.data[0].artifact_metadata == {"pageTitle": "Decision"}
    assert raw_artifacts.total == 1
    assert [job.provider_job_id for job in provider_jobs.data] == [provider_job.provider_job_id]
    assert provider_jobs.data[0].status is ProviderJobStatus.COMPLETED
    assert provider_jobs.data[0].last_event_type == "crawl.completed"
    assert provider_jobs.total == 1


@pytest.mark.asyncio
async def test_run_scoped_captured_resource_list_is_paginated(session) -> None:
    source, version, source_service = await _seed_source_version(session)
    await source_service.approve_source_version(version.source_version_id)
    run = await RunService(session, StubProvider()).create_run(
        CreateRunRequest(
            source_id=source.source_id,
            source_version_id=version.source_version_id,
            mode=RunMode.PREVIEW,
        )
    )
    for i in range(3):
        artifact_id = f"art_pag_{i}"
        session.add(
            RawArtifact(
                artifact_id=artifact_id,
                run_id=run.run_id,
                source_id=source.source_id,
                source_version_id=version.source_version_id,
                storage_path=f"gs://bucket/{artifact_id}",
                content_type="text/html",
                artifact_metadata={},
            )
        )
        await session.flush()
        session.add(
            CapturedResource(
                captured_resource_id=f"cap_pag_{i}",
                artifact_id=artifact_id,
                run_id=run.run_id,
                source_id=source.source_id,
                source_version_id=version.source_version_id,
                provider_job_id=None,
                source_url=f"https://example.com/{i}",
                final_url=f"https://example.com/{i}",
                title=f"Page {i}",
                content_type="text/html",
                checksum=f"chk_{i}",
                http_status=200,
                discovery_depth=1,
            )
        )
        await session.flush()
    await session.commit()

    run_service = RunService(session)
    first_page = await run_service.list_captured_resources(run.run_id, limit=2, offset=0)
    second_page = await run_service.list_captured_resources(run.run_id, limit=2, offset=2)

    assert first_page.total == 3
    assert len(first_page.data) == 2
    assert second_page.total == 3
    assert len(second_page.data) == 1
    seen = {r.captured_resource_id for r in first_page.data} | {
        r.captured_resource_id for r in second_page.data
    }
    assert len(seen) == 3


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
async def test_retry_run_redispatches_when_inline_backend(session) -> None:
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
    run.status = RunStatus.FAILED
    run.failure_reason = "provider timeout"
    run.completed_at = run.created_at
    await session.commit()

    retried = await run_service.retry_run(run.run_id)

    assert retried.status is RunStatus.RUNNING
    assert retried.failure_reason is None
    assert retried.started_at is not None
    assert retried.completed_at is None


@pytest.mark.asyncio
async def test_retry_run_worker_backend_leaves_pending_and_clears_provider_jobs(
    session,
) -> None:
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
    session.add(
        ProviderJob(
            run_id=run.run_id,
            provider="firecrawl",
            external_job_id="stale_worker_retry_job",
            status=ProviderJobStatus.FAILED,
            request_payload={},
            response_payload={},
        )
    )
    run.status = RunStatus.FAILED
    run.failure_reason = "worker never completed"
    run.completed_at = run.created_at
    await session.commit()

    retried = await run_service.retry_run(run.run_id)

    assert retried.status is RunStatus.PENDING
    assert retried.failure_reason is None
    assert retried.started_at is None
    assert retried.completed_at is None

    jobs = list(await session.scalars(select(ProviderJob).where(ProviderJob.run_id == run.run_id)))
    assert jobs == []


@pytest.mark.asyncio
async def test_retry_run_rejects_non_terminal_states(session) -> None:
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

    with pytest.raises(InvalidStateTransitionError):
        await run_service.retry_run(run.run_id)


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


@pytest.mark.asyncio
async def test_provider_registry_dispatches_deterministic_inline_runs(session) -> None:
    source, version, source_service = await _seed_source_version(session)
    await source_service.approve_source_version(version.source_version_id)
    version.acquisition_spec = {
        "provider": "deterministic_http",
        "seed_url": "https://example.com/decisions/2026-01?utm_source=test",
        "mode": "crawl",
    }
    await session.commit()

    registry = ProviderRegistry()
    registry.register(StubProvider())
    registry.register(InlineDeterministicProvider())

    artifact_store = InMemoryArtifactStore()
    publisher = RecordingPublisher()
    run_service = RunService(
        session,
        provider_registry=registry,
        artifact_store=artifact_store,
        publisher=publisher,
    )
    run = await run_service.create_run(
        CreateRunRequest(
            source_id=source.source_id,
            source_version_id=version.source_version_id,
            mode=RunMode.PRODUCTION,
        )
    )
    provider_job = await session.scalar(select(ProviderJob).where(ProviderJob.run_id == run.run_id))

    assert run.status is RunStatus.COMPLETED
    assert run.artifacts_count == 1
    assert run.captured_resources_count == 1
    assert provider_job is not None
    assert provider_job.provider == "deterministic_http"
    assert provider_job.status is ProviderJobStatus.COMPLETED
    assert publisher.raw_artifact_ids is not None
    assert len(publisher.raw_artifact_ids) == 1
    assert publisher.bundle_events is not None
    assert len(publisher.bundle_events) == 1
    assert publisher.bundle_events[0]["event_type"] == "artifact_bundle.available"
    assert publisher.bundle_events[0]["payload"]["provenance"]["run_id"] == run.run_id
    assert artifact_store.stored_manifests is not None
    assert len(artifact_store.stored_manifests) == 1
    manifest = next(iter(artifact_store.stored_manifests.values()))
    assert manifest["bundle_metadata"]["extraction_hints"]["authority_display_hint"] == (
        "Zurich Administrative Court"
    )


@pytest.mark.asyncio
async def test_provider_registry_dispatches_fedlex_sparql_runs(session) -> None:
    source, version, source_service = await _seed_source_version(session)
    await source_service.approve_source_version(version.source_version_id)
    version.acquisition_spec = {
        "provider": "fedlex_sparql",
        "seed_url": "https://fedlex.data.admin.ch/eli/cc/1999/404",
        "sparql_endpoint": "https://fedlex.data.admin.ch/sparqlendpoint",
        "language_codes": ["de", "fr", "it"],
        "document_type_hint": "legislation",
    }
    await session.commit()

    registry = ProviderRegistry()
    registry.register(StubProvider())
    registry.register(FedlexSparqlProviderStub())

    run_service = RunService(session, provider_registry=registry)
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
    assert provider_job.provider == "fedlex_sparql"
    assert provider_job.external_job_id == "sparql_job_001"
    assert (
        provider_job.request_payload["work_uri"] == "https://fedlex.data.admin.ch/eli/cc/1999/404"
    )
    assert provider_job.response_payload["expression_uris"] == [
        "https://fedlex.data.admin.ch/eli/cc/1999/404/de",
        "https://fedlex.data.admin.ch/eli/cc/1999/404/fr",
    ]


@pytest.mark.asyncio
async def test_provider_registry_publishes_bundle_for_json_only_inline_artifact(session) -> None:
    source, version, source_service = await _seed_source_version(session)
    await source_service.approve_source_version(version.source_version_id)
    version.acquisition_spec = {
        "provider": "deterministic_http",
        "seed_url": "https://registry.npmjs.org/left-pad/latest",
        "mode": "crawl",
    }
    await session.commit()

    registry = ProviderRegistry()
    registry.register(StubProvider())
    registry.register(InlineJsonDeterministicProvider())

    artifact_store = InMemoryArtifactStore()
    publisher = RecordingPublisher()
    run_service = RunService(
        session,
        provider_registry=registry,
        artifact_store=artifact_store,
        publisher=publisher,
    )
    run = await run_service.create_run(
        CreateRunRequest(
            source_id=source.source_id,
            source_version_id=version.source_version_id,
            mode=RunMode.PRODUCTION,
        )
    )

    assert run.status is RunStatus.COMPLETED
    assert publisher.bundle_events is not None
    assert len(publisher.bundle_events) == 1
    assert publisher.bundle_events[0]["event_type"] == "artifact_bundle.available"


@pytest.mark.asyncio
async def test_get_pipeline_health_summarizes_run_processing_and_search_stage(session) -> None:
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
    run.status = RunStatus.COMPLETED
    run.completed_at = run.created_at
    session.add(
        ProcessingStatusUpdate(
            event_id="evt_ps_1",
            run_id=run.run_id,
            processing_manifest_id="pm_1",
            processing_version="2026.04",
            status=ProcessingStatus.CANONICAL_READY,
            occurred_at=run.created_at,
            source_snapshot_id="snap_1",
            bundle_manifest_id="abm_1",
            document_id="doc_1",
            document_revision=1,
            error_code=None,
            error_summary=None,
        )
    )
    session.add(
        DocumentLifecycleEvent(
            event_id="evt_dl_1",
            event_type="document.processed",
            run_id=run.run_id,
            document_id="doc_1",
            document_revision=1,
            processing_manifest_id="pm_1",
            processing_version="2026.04",
            lifecycle_status="active",
            reason_code=None,
            reason_summary=None,
            search_disposition=None,
            occurred_at=run.created_at,
        )
    )
    await session.commit()

    pipeline = await run_service.get_pipeline_health(run.run_id)
    by_stage = {stage.stage: stage for stage in pipeline.stages}

    assert pipeline.overall_status == "ok"
    assert pipeline.processing_status_event_count == 1
    assert pipeline.document_lifecycle_event_count == 1
    assert by_stage["acquisition"].status == "ok"
    assert by_stage["document_intelligence"].status == "ok"
    assert by_stage["projection"].status == "ok"
    assert by_stage["search"].status == "ok"


@pytest.mark.asyncio
async def test_dispatch_pending_runs_does_not_publish_before_commit(session) -> None:
    source, version, source_service = await _seed_source_version(session)
    await source_service.approve_source_version(version.source_version_id)
    version.acquisition_spec = {
        "provider": "deterministic_http",
        "seed_url": "https://example.com/decisions/2026-01?utm_source=test",
        "mode": "crawl",
    }
    await session.commit()

    registry = ProviderRegistry()
    registry.register(FlakyInlineDeterministicProvider())

    artifact_store = InMemoryArtifactStore()
    publisher = RecordingPublisher()
    run_service = RunService(
        session,
        provider_registry=registry,
        artifact_store=artifact_store,
        publisher=publisher,
        run_dispatch_backend="worker",
    )
    await run_service.create_run(
        CreateRunRequest(
            source_id=source.source_id,
            source_version_id=version.source_version_id,
            mode=RunMode.PRODUCTION,
        )
    )
    await run_service.create_run(
        CreateRunRequest(
            source_id=source.source_id,
            source_version_id=version.source_version_id,
            mode=RunMode.PRODUCTION,
        )
    )

    with pytest.raises(RuntimeError, match="simulated provider failure"):
        await run_service.dispatch_pending_runs(limit=10)
    await session.rollback()

    assert publisher.raw_artifact_ids == []
    assert publisher.bundle_events == []
