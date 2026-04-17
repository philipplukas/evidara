from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest
from sqlalchemy import select

from platform_control.domain import (
    ProviderJobStatus,
    RunMode,
    RunStatus,
    SourceVersionStatus,
)
from platform_control.events.publisher import RawArtifactPublisher
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.compliance_policy import CompliancePolicy
from platform_control.models.provider_job import ProviderJob
from platform_control.models.raw_artifact import RawArtifact
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.services.artifact_store import LocalArtifactStore
from platform_control.services.firecrawl_webhook_service import FirecrawlWebhookService


class _CollectingPublisher(RawArtifactPublisher):
    def __init__(self) -> None:
        self.published: list[str] = []
        self.bundles: list[dict[str, object]] = []

    async def publish_raw_artifact_available(self, artifact: RawArtifact) -> None:
        self.published.append(artifact.artifact_id)

    async def publish_artifact_bundle_available(self, event: dict[str, object]) -> None:
        self.bundles.append(event)


async def _seed_jurisdiction(
    session,
    *,
    attribution_required: bool,
    attribution_text: str | None,
) -> None:
    policy = CompliancePolicy(
        name="ch-attribution",
        attribution_required=attribution_required,
        attribution_text=attribution_text,
        contact_url="https://evidara.ai/contact",
    )
    session.add(policy)
    await session.flush()
    session.add(
        Jurisdiction(
            jurisdiction_id="jur_ch",
            name="Switzerland",
            slug="ch",
            compliance_policy_id=policy.compliance_policy_id,
        )
    )
    session.add(
        Authority(
            authority_id="auth_zh_admin",
            jurisdiction_id="jur_ch",
            name="Zurich Administrative Court",
            slug="zh-admin-court",
        )
    )
    session.add_all(
        [
            Source(
                source_id="src_attr",
                name="Zurich decisions",
                jurisdiction_id="jur_ch",
                authority_id="auth_zh_admin",
            ),
            SourceVersion(
                source_version_id="sv_attr",
                source_id="src_attr",
                version_label="v1",
                status=SourceVersionStatus.APPROVED,
                acquisition_spec={
                    "provider": "firecrawl",
                    "mode": "crawl",
                    "seed_url": "https://example.com/decisions",
                },
            ),
            Run(
                run_id="run_attr",
                source_id="src_attr",
                source_version_id="sv_attr",
                mode=RunMode.PREVIEW,
                status=RunStatus.RUNNING,
            ),
            ProviderJob(
                provider_job_id="pjob_attr",
                run_id="run_attr",
                external_job_id="crawl_attr",
                status=ProviderJobStatus.RUNNING,
                request_payload={},
                response_payload={},
            ),
        ]
    )
    await session.commit()


def _signed(payload: dict[str, object], secret: str) -> tuple[bytes, str]:
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    signature = (
        "sha256=" + hmac.new(secret.encode("utf-8"), body, digestmod=hashlib.sha256).hexdigest()
    )
    return body, signature


async def _drive_crawl_through_completion(
    session, service: FirecrawlWebhookService, secret: str
) -> None:
    page = {
        "type": "crawl.page",
        "id": "crawl_attr",
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
    body, sig = _signed(page, secret)
    await service.process(payload=page, raw_body=body, signature=sig)

    completed = {"type": "crawl.completed", "id": "crawl_attr", "data": {}}
    body, sig = _signed(completed, secret)
    await service.process(payload=completed, raw_body=body, signature=sig)


@pytest.mark.asyncio
async def test_attribution_block_included_when_policy_requires_it(session, tmp_path: Path) -> None:
    await _seed_jurisdiction(
        session,
        attribution_required=True,
        attribution_text="Source: Canton of Zurich — open-data licence.",
    )
    publisher = _CollectingPublisher()
    service = FirecrawlWebhookService(
        session=session,
        artifact_store=LocalArtifactStore(tmp_path / "artifacts"),
        publisher=publisher,
        webhook_secret="test-secret",
    )

    await _drive_crawl_through_completion(session, service, secret="test-secret")

    assert publisher.bundles, "bundle event was not published"
    payload = publisher.bundles[0]["payload"]  # type: ignore[index]
    manifest_storage_ref = payload["bundle_manifest_ref"]["storage_ref"]  # type: ignore[index]
    manifest_uri = str(manifest_storage_ref["uri"])  # type: ignore[index]
    manifest = json.loads(Path(manifest_uri.removeprefix("file://")).read_text())
    attribution = manifest["bundle_metadata"].get("attribution")
    assert attribution is not None
    assert attribution["required"] is True
    assert attribution["text"] == "Source: Canton of Zurich — open-data licence."
    assert attribution["contact_url"] == "https://evidara.ai/contact"


@pytest.mark.asyncio
async def test_attribution_block_absent_when_not_required(session, tmp_path: Path) -> None:
    await _seed_jurisdiction(session, attribution_required=False, attribution_text="ignored")
    publisher = _CollectingPublisher()
    service = FirecrawlWebhookService(
        session=session,
        artifact_store=LocalArtifactStore(tmp_path / "artifacts"),
        publisher=publisher,
        webhook_secret="test-secret",
    )

    await _drive_crawl_through_completion(session, service, secret="test-secret")

    payload = publisher.bundles[0]["payload"]  # type: ignore[index]
    manifest_storage_ref = payload["bundle_manifest_ref"]["storage_ref"]  # type: ignore[index]
    manifest_uri = str(manifest_storage_ref["uri"])  # type: ignore[index]
    manifest = json.loads(Path(manifest_uri.removeprefix("file://")).read_text())
    assert "attribution" not in manifest["bundle_metadata"]


@pytest.mark.asyncio
async def test_webhook_record_dir_mirrors_payload_to_disk(session, tmp_path: Path) -> None:
    await _seed_jurisdiction(session, attribution_required=False, attribution_text=None)
    record_dir = tmp_path / "webhook-log"
    publisher = _CollectingPublisher()
    service = FirecrawlWebhookService(
        session=session,
        artifact_store=LocalArtifactStore(tmp_path / "artifacts"),
        publisher=publisher,
        webhook_secret="test-secret",
        webhook_record_dir=record_dir,
    )

    page = {
        "type": "crawl.page",
        "id": "crawl_attr",
        "data": {
            "url": "https://example.com/decisions/1",
            "markdown": "# Decision",
            "metadata": {"sourceURL": "https://example.com/decisions/1"},
        },
    }
    body, sig = _signed(page, "test-secret")
    await service.process(payload=page, raw_body=body, signature=sig)

    job_dir = record_dir / "crawl_attr"
    assert job_dir.exists()
    recorded_files = list(job_dir.glob("*_crawl_page.json"))
    assert len(recorded_files) == 1
    contents = json.loads(recorded_files[0].read_text())
    assert contents["type"] == "crawl.page"
    assert contents["id"] == "crawl_attr"


@pytest.mark.asyncio
async def test_webhook_record_dir_absent_by_default(session, tmp_path: Path) -> None:
    await _seed_jurisdiction(session, attribution_required=False, attribution_text=None)
    publisher = _CollectingPublisher()
    service = FirecrawlWebhookService(
        session=session,
        artifact_store=LocalArtifactStore(tmp_path / "artifacts"),
        publisher=publisher,
        webhook_secret="test-secret",
    )

    page = {
        "type": "crawl.page",
        "id": "crawl_attr",
        "data": {"url": "https://example.com/decisions/1", "metadata": {}},
    }
    body, sig = _signed(page, "test-secret")
    await service.process(payload=page, raw_body=body, signature=sig)

    # Nothing mirrored to tmp_path beyond the artifact store directory.
    assert not any(entry.name == "webhook-log" for entry in tmp_path.iterdir())
    # Sanity: ingest still happened.
    artifact_count = await session.scalar(select(RawArtifact.artifact_id))
    assert artifact_count is not None
