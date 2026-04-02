from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from platform_control.domain import ProviderJobStatus, RunMode, RunStatus, SourceVersionStatus
from platform_control.events.publisher import RawArtifactPublisher
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.provider_job import ProviderJob
from platform_control.models.raw_artifact import RawArtifact
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.models.webhook_receipt import WebhookReceipt
from platform_control.services.artifact_store import LocalArtifactStore
from platform_control.services.firecrawl_webhook_service import FirecrawlWebhookService


class CollectingPublisher(RawArtifactPublisher):
    def __init__(self) -> None:
        self.published_ids: list[str] = []

    async def publish_raw_artifact_available(self, artifact: RawArtifact) -> None:
        self.published_ids.append(artifact.artifact_id)


@pytest.mark.asyncio
async def test_webhook_processing_is_idempotent(session, tmp_path: Path) -> None:
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
        source_id="src_seed",
        name="Zurich decisions",
        jurisdiction_id="jur_ch",
        authority_id="auth_zh_admin",
    )
    source_version = SourceVersion(
        source_version_id="sv_seed",
        source_id="src_seed",
        version_label="v1",
        status=SourceVersionStatus.APPROVED,
        acquisition_spec={"seed_url": "https://example.com/decisions", "mode": "crawl"},
    )
    run = Run(
        run_id="run_seed",
        source_id="src_seed",
        source_version_id="sv_seed",
        mode=RunMode.PREVIEW,
        status=RunStatus.RUNNING,
    )
    provider_job = ProviderJob(
        provider_job_id="pjob_seed",
        run_id="run_seed",
        external_job_id="crawl_123",
        status=ProviderJobStatus.RUNNING,
        request_payload={},
        response_payload={},
    )
    session.add_all([source, source_version, run, provider_job])
    await session.commit()

    payload = {
        "type": "crawl.page",
        "id": "crawl_123",
        "data": {
            "url": "https://example.com/decisions/1",
            "markdown": "# Decision",
            "metadata": {
                "title": "Decision 1",
                "sourceURL": "https://example.com/decisions/1",
                "statusCode": 200,
                "depth": 1,
                "contentType": "text/html",
            },
        },
    }
    raw_body = json.dumps(payload, sort_keys=True).encode("utf-8")
    signature = (
        "sha256="
        + hmac.new(
            b"test-secret",
            raw_body,
            digestmod=hashlib.sha256,
        ).hexdigest()
    )

    publisher = CollectingPublisher()
    service = FirecrawlWebhookService(
        session=session,
        artifact_store=LocalArtifactStore(base_dir=tmp_path / "artifacts"),
        publisher=publisher,
        webhook_secret="test-secret",
    )

    await service.process(payload=payload, raw_body=raw_body, signature=signature)
    await service.process(payload=payload, raw_body=raw_body, signature=signature)

    receipt_count = await session.scalar(select(func.count()).select_from(WebhookReceipt))
    artifact_count = await session.scalar(select(func.count()).select_from(RawArtifact))

    assert receipt_count == 1
    assert artifact_count == 1
    assert publisher.published_ids
