from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest
from sqlalchemy import select

from platform_control.domain import ProviderJobStatus, RunMode, RunStatus, SourceVersionStatus
from platform_control.events.publisher import RawArtifactPublisher
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.captured_resource import CapturedResource
from platform_control.models.provider_job import ProviderJob
from platform_control.models.raw_artifact import RawArtifact
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.services.artifact_store import LocalArtifactStore
from platform_control.services.firecrawl_webhook_service import FirecrawlWebhookService


class CollectingPublisher(RawArtifactPublisher):
    def __init__(self) -> None:
        self.published_ids: list[str] = []
        self.bundle_events: list[dict[str, object]] = []

    async def publish_raw_artifact_available(self, artifact: RawArtifact) -> None:
        self.published_ids.append(artifact.artifact_id)

    async def publish_artifact_bundle_available(self, event: dict[str, object]) -> None:
        self.bundle_events.append(event)


async def _seed_run_graph(session) -> ProviderJob:
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

    source = Source(
        source_id="src_failure_seed",
        name="Zurich decisions",
        jurisdiction_id="jur_ch",
        authority_id="auth_zh_admin",
    )
    source_version = SourceVersion(
        source_version_id="sv_failure_seed",
        source_id="src_failure_seed",
        version_label="v1",
        status=SourceVersionStatus.APPROVED,
        acquisition_spec={
            "seed_url": "https://example.com/decisions",
            "mode": "crawl",
            "tenant_id": "tenant_public",
            "corpus_id": "corpus_public_ch_admin_decisions",
            "scope_type": "global_public",
            "source_origin_kind": "official_primary",
            "trust_tier": "authoritative",
        },
    )
    run = Run(
        run_id="run_failure_seed",
        source_id="src_failure_seed",
        source_version_id="sv_failure_seed",
        mode=RunMode.PREVIEW,
        status=RunStatus.RUNNING,
    )
    provider_job = ProviderJob(
        provider_job_id="pjob_failure_seed",
        run_id="run_failure_seed",
        external_job_id="crawl_failure_123",
        status=ProviderJobStatus.RUNNING,
        request_payload={},
        response_payload={},
    )
    session.add_all([source, source_version, run, provider_job])
    await session.commit()
    return provider_job


def _signed_body(payload: dict[str, object]) -> tuple[bytes, str]:
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    signature = "sha256=" + hmac.new(b"test-secret", body, digestmod=hashlib.sha256).hexdigest()
    return body, signature


@pytest.mark.asyncio
async def test_crawl_failed_marks_run_and_provider_job_failed(session, tmp_path: Path) -> None:
    await _seed_run_graph(session)
    publisher = CollectingPublisher()
    service = FirecrawlWebhookService(
        session=session,
        artifact_store=LocalArtifactStore(base_dir=tmp_path / "artifacts"),
        publisher=publisher,
        webhook_secret="test-secret",
    )
    payload = {"type": "crawl.failed", "id": "crawl_failure_123", "error": "upstream timeout"}
    body, signature = _signed_body(payload)

    await service.process(payload=payload, raw_body=body, signature=signature)

    provider_job = await session.scalar(
        select(ProviderJob).where(ProviderJob.external_job_id == "crawl_failure_123")
    )
    run = await session.get(Run, "run_failure_seed")
    assert provider_job is not None
    assert run is not None
    assert provider_job.status is ProviderJobStatus.FAILED
    assert provider_job.last_event_type == "crawl.failed"
    assert run.status is RunStatus.FAILED
    assert run.failure_reason == "upstream timeout"
    assert run.completed_at is not None
    assert publisher.bundle_events == []


@pytest.mark.asyncio
async def test_crawl_completed_without_artifacts_sets_completed_but_skips_bundle_event(
    session, tmp_path: Path
) -> None:
    await _seed_run_graph(session)
    publisher = CollectingPublisher()
    service = FirecrawlWebhookService(
        session=session,
        artifact_store=LocalArtifactStore(base_dir=tmp_path / "artifacts"),
        publisher=publisher,
        webhook_secret="test-secret",
    )
    payload = {"type": "crawl.completed", "id": "crawl_failure_123", "data": {}}
    body, signature = _signed_body(payload)

    await service.process(payload=payload, raw_body=body, signature=signature)

    provider_job = await session.scalar(
        select(ProviderJob).where(ProviderJob.external_job_id == "crawl_failure_123")
    )
    run = await session.get(Run, "run_failure_seed")
    assert provider_job is not None
    assert run is not None
    assert provider_job.status is ProviderJobStatus.COMPLETED
    assert run.status is RunStatus.COMPLETED
    assert run.completed_at is not None
    assert publisher.bundle_events == []


@pytest.mark.asyncio
async def test_malformed_crawl_page_entries_are_ignored_without_failing_webhook_processing(
    session, tmp_path: Path
) -> None:
    await _seed_run_graph(session)
    publisher = CollectingPublisher()
    service = FirecrawlWebhookService(
        session=session,
        artifact_store=LocalArtifactStore(base_dir=tmp_path / "artifacts"),
        publisher=publisher,
        webhook_secret="test-secret",
    )
    payload = {
        "type": "crawl.page",
        "id": "crawl_failure_123",
        "data": [
            "not-a-page-object",
            {
                "url": "https://example.com/decisions/123",
                "markdown": "# Decision",
                "metadata": {
                    "title": "Decision 123",
                    "sourceURL": "https://example.com/decisions/123",
                    "statusCode": 200,
                    "depth": 1,
                },
            },
        ],
    }
    body, signature = _signed_body(payload)

    await service.process(payload=payload, raw_body=body, signature=signature)

    artifacts = list(await session.scalars(select(RawArtifact).where(RawArtifact.run_id == "run_failure_seed")))
    resources = list(
        await session.scalars(
            select(CapturedResource).where(CapturedResource.run_id == "run_failure_seed")
        )
    )
    run = await session.get(Run, "run_failure_seed")
    assert run is not None
    assert len(artifacts) == 1
    assert len(resources) == 1
    assert resources[0].final_url == "https://example.com/decisions/123"
    assert resources[0].content_type == "text/html"
    assert run.artifacts_count == 1
    assert run.captured_resources_count == 1
    assert len(publisher.published_ids) == 1


@pytest.mark.asyncio
async def test_crawl_failed_without_error_uses_default_failure_reason(session, tmp_path: Path) -> None:
    await _seed_run_graph(session)
    publisher = CollectingPublisher()
    service = FirecrawlWebhookService(
        session=session,
        artifact_store=LocalArtifactStore(base_dir=tmp_path / "artifacts"),
        publisher=publisher,
        webhook_secret="test-secret",
    )
    payload = {"type": "crawl.failed", "id": "crawl_failure_123", "data": {}}
    body, signature = _signed_body(payload)

    await service.process(payload=payload, raw_body=body, signature=signature)

    run = await session.get(Run, "run_failure_seed")
    assert run is not None
    assert run.status is RunStatus.FAILED
    assert run.failure_reason == "Firecrawl job failed."
    assert run.completed_at is not None

