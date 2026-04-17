from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from platform_control.cli.ingest import ingest_payloads, load_payloads
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


class _CollectingPublisher(RawArtifactPublisher):
    def __init__(self) -> None:
        self.published: list[str] = []
        self.bundles: list[dict[str, object]] = []

    async def publish_raw_artifact_available(self, artifact: RawArtifact) -> None:
        self.published.append(artifact.artifact_id)

    async def publish_artifact_bundle_available(self, event: dict[str, object]) -> None:
        self.bundles.append(event)


async def _seed_run(session) -> None:
    session.add(Jurisdiction(jurisdiction_id="jur_ch", name="Switzerland", slug="ch"))
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
                source_id="src_seed",
                name="Zurich decisions",
                jurisdiction_id="jur_ch",
                authority_id="auth_zh_admin",
            ),
            SourceVersion(
                source_version_id="sv_seed",
                source_id="src_seed",
                version_label="v1",
                status=SourceVersionStatus.APPROVED,
                acquisition_spec={
                    "provider": "firecrawl",
                    "mode": "crawl",
                    "seed_url": "https://example.com/decisions",
                },
            ),
            Run(
                run_id="run_seed",
                source_id="src_seed",
                source_version_id="sv_seed",
                mode=RunMode.PREVIEW,
                status=RunStatus.RUNNING,
            ),
            ProviderJob(
                provider_job_id="pjob_seed",
                run_id="run_seed",
                external_job_id="crawl_fixture",
                status=ProviderJobStatus.RUNNING,
                request_payload={},
                response_payload={},
            ),
        ]
    )
    await session.commit()


def _page_payload() -> dict[str, object]:
    return {
        "type": "crawl.page",
        "id": "crawl_fixture",
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


def test_load_payloads_accepts_single_object(tmp_path: Path) -> None:
    fixture = tmp_path / "single.json"
    fixture.write_text(json.dumps(_page_payload()))

    loaded = load_payloads(fixture)

    assert len(loaded) == 1
    assert loaded[0]["id"] == "crawl_fixture"


def test_load_payloads_accepts_array(tmp_path: Path) -> None:
    fixture = tmp_path / "many.json"
    fixture.write_text(json.dumps([_page_payload(), _page_payload()]))

    loaded = load_payloads(fixture)

    assert len(loaded) == 2


def test_load_payloads_rejects_non_object_root(tmp_path: Path) -> None:
    fixture = tmp_path / "bad.json"
    fixture.write_text(json.dumps("not-an-object"))

    with pytest.raises(ValueError):
        load_payloads(fixture)


@pytest.mark.asyncio
async def test_ingest_payloads_drives_process_payload(session, tmp_path: Path) -> None:
    await _seed_run(session)
    publisher = _CollectingPublisher()
    service = FirecrawlWebhookService(
        session=session,
        artifact_store=LocalArtifactStore(base_dir=tmp_path / "artifacts"),
        publisher=publisher,
        webhook_secret=None,
    )

    processed = await ingest_payloads([_page_payload()], service=service)

    assert processed == 1
    receipt_count = await session.scalar(select(func.count()).select_from(WebhookReceipt))
    artifact_count = await session.scalar(select(func.count()).select_from(RawArtifact))
    assert receipt_count == 1
    assert artifact_count == 1
    assert publisher.published


@pytest.mark.asyncio
async def test_ingest_payloads_is_idempotent_across_replays(session, tmp_path: Path) -> None:
    await _seed_run(session)
    publisher = _CollectingPublisher()
    service = FirecrawlWebhookService(
        session=session,
        artifact_store=LocalArtifactStore(base_dir=tmp_path / "artifacts"),
        publisher=publisher,
        webhook_secret=None,
    )
    payload = _page_payload()

    await ingest_payloads([payload], service=service)
    await ingest_payloads([payload], service=service)

    receipt_count = await session.scalar(select(func.count()).select_from(WebhookReceipt))
    artifact_count = await session.scalar(select(func.count()).select_from(RawArtifact))
    assert receipt_count == 1
    assert artifact_count == 1
