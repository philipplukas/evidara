from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from prometheus_client import REGISTRY
from sqlalchemy import func, select

from platform_control.domain import ProviderJobStatus, RunMode, RunStatus, SourceVersionStatus
from platform_control.errors import SignatureVerificationError, WebhookRetryableError
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
        self.bundle_events: list[dict[str, object]] = []

    async def publish_raw_artifact_available(self, artifact: RawArtifact) -> None:
        self.published_ids.append(artifact.artifact_id)

    async def publish_artifact_bundle_available(self, event: dict[str, object]) -> None:
        self.bundle_events.append(event)


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
        acquisition_spec={
            "seed_url": "https://example.com/decisions",
            "mode": "crawl",
            "tenant_id": "tenant_public",
            "corpus_id": "corpus_public_ch_admin_decisions",
            "scope_type": "global_public",
            "source_origin_kind": "official_primary",
            "trust_tier": "authoritative",
            "language_codes": ["de"],
            "document_type_hint": "decision",
        },
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

    crawl_page_payload = {
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
    page_body = json.dumps(crawl_page_payload, sort_keys=True).encode("utf-8")
    page_signature = (
        "sha256="
        + hmac.new(
            b"test-secret",
            page_body,
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

    await service.process(payload=crawl_page_payload, raw_body=page_body, signature=page_signature)
    await service.process(payload=crawl_page_payload, raw_body=page_body, signature=page_signature)

    await session.refresh(run)
    checkpoint = run.run_metadata.get("replay_checkpoint") or {}
    assert checkpoint.get("last_firecrawl_event_type") == "crawl.page"
    assert checkpoint.get("pages_ingested") == 1

    crawl_completed_payload = {"type": "crawl.completed", "id": "crawl_123", "data": {}}
    completed_body = json.dumps(crawl_completed_payload, sort_keys=True).encode("utf-8")
    completed_signature = (
        "sha256="
        + hmac.new(
            b"test-secret",
            completed_body,
            digestmod=hashlib.sha256,
        ).hexdigest()
    )
    await service.process(
        payload=crawl_completed_payload,
        raw_body=completed_body,
        signature=completed_signature,
    )

    receipt_count = await session.scalar(select(func.count()).select_from(WebhookReceipt))
    artifact_count = await session.scalar(select(func.count()).select_from(RawArtifact))

    assert receipt_count == 2
    assert artifact_count == 1
    assert publisher.published_ids
    assert publisher.bundle_events
    bundle_event = publisher.bundle_events[0]
    payload = bundle_event["payload"]  # type: ignore[index]
    manifest_storage_ref = payload["bundle_manifest_ref"]["storage_ref"]  # type: ignore[index]
    assert bundle_event["event_type"] == "artifact_bundle.available"
    assert payload["provenance"]["run_id"] == "run_seed"  # type: ignore[index]
    assert payload["provenance"]["tenant_id"] == "tenant_public"  # type: ignore[index]
    assert payload["provenance"]["corpus_id"] == "corpus_public_ch_admin_decisions"  # type: ignore[index]
    assert payload["provenance"]["scope_type"] == "global_public"  # type: ignore[index]
    assert payload["source_origin_kind"] == "official_primary"  # type: ignore[index]
    assert payload["trust_tier"] == "authoritative"  # type: ignore[index]
    assert str(manifest_storage_ref["uri"]).startswith("file://")  # type: ignore[index]

    manifest_uri = str(manifest_storage_ref["uri"])  # type: ignore[index]
    manifest_path = Path(manifest_uri.removeprefix("file://"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    extraction_hints = manifest["bundle_metadata"]["extraction_hints"]
    assert extraction_hints["title_hint"] == "Decision 1"
    assert extraction_hints["document_type_hint"] == "decision"
    assert extraction_hints["authority_display_hint"] == "Zurich Administrative Court"
    assert manifest["source_defaults"]["language_codes"] == ["de"]
    assert manifest["source_defaults"]["document_type_hint"] == "decision"
    # Contract uses latest_approved policy => pinned ref must remain null.
    assert manifest["reference_context"]["reference_snapshot_set_ref"] is None
    reference_snapshot_export = manifest["bundle_metadata"]["reference_snapshot_export"]
    assert str(reference_snapshot_export["reference_snapshot_set_id"]).startswith("rss_")
    snapshot_uri = str(reference_snapshot_export["storage_ref"]["uri"])
    assert snapshot_uri.startswith("file://")
    snapshot_path = Path(snapshot_uri.removeprefix("file://"))
    snapshot_payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot_payload["provenance"]["run_id"] == "run_seed"
    assert snapshot_payload["jurisdictions"] == [{"jurisdiction_id": "jur_ch"}]


def test_storage_ref_marks_uri_hash_when_checksum_is_unavailable() -> None:
    artifact = RawArtifact(
        artifact_id="art_123",
        run_id="run_123",
        source_id="src_123",
        source_version_id="sv_123",
        storage_path="gs://bucket/path/art_123.json",
        content_type="application/json",
        artifact_metadata={},
        created_at=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
    )

    storage_ref = FirecrawlWebhookService._build_storage_ref_for_artifact(artifact)

    assert storage_ref["checksum_algorithm"] == "uri-hash"
    assert len(str(storage_ref["checksum"])) == 64


@pytest.mark.asyncio
async def test_webhook_processing_rejects_tampered_signature(session, tmp_path: Path) -> None:
    publisher = CollectingPublisher()
    service = FirecrawlWebhookService(
        session=session,
        artifact_store=LocalArtifactStore(base_dir=tmp_path / "artifacts"),
        publisher=publisher,
        webhook_secret="test-secret",
    )

    with pytest.raises(SignatureVerificationError):
        await service.process(
            payload={"type": "crawl.page", "id": "crawl_123", "data": {}},
            raw_body=b"{}",
            signature="sha256=definitely-wrong",
        )


# --- #558: a delivery we did not apply must never spend its dedupe key -------------


async def _seed_run_without_provider_job(session) -> Run:
    """Seed the exact state of the dispatch race: the Run exists, the ProviderJob (whose
    external_job_id only exists once Firecrawl's POST has returned) does not yet."""
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
        source_id="src_race",
        name="Zurich decisions",
        jurisdiction_id="jur_ch",
        authority_id="auth_zh_admin",
    )
    source_version = SourceVersion(
        source_version_id="sv_race",
        source_id="src_race",
        version_label="v1",
        status=SourceVersionStatus.APPROVED,
        acquisition_spec={"seed_url": "https://example.com/decisions", "mode": "crawl"},
    )
    run = Run(
        run_id="run_race",
        source_id="src_race",
        source_version_id="sv_race",
        mode=RunMode.PREVIEW,
        status=RunStatus.PENDING,
    )
    session.add_all([source, source_version, run])
    await session.commit()
    return run


def _service(session, tmp_path: Path) -> FirecrawlWebhookService:
    return FirecrawlWebhookService(
        session=session,
        artifact_store=LocalArtifactStore(base_dir=tmp_path / "artifacts"),
        publisher=CollectingPublisher(),
        webhook_secret="test-secret",
    )


def _unmatched_count(event_type: str, reason: str) -> float:
    value = REGISTRY.get_sample_value(
        "platform_control_firecrawl_webhooks_unmatched_total",
        {"event_type": event_type, "reason": reason},
    )
    return 0.0 if value is None else value


@pytest.mark.asyncio
async def test_webhook_racing_the_provider_job_commit_survives_redelivery(
    session, tmp_path: Path
) -> None:
    """The #558 regression: `crawl.started` arrives before the ProviderJob is committed.

    The old code consumed the dedupe key anyway (receipt written as processed) and skipped
    the event, so Firecrawl's identical retry was deduped away and the run stayed RUNNING
    forever. The delivery must instead be kept reclaimable and the retry must apply it.
    """
    run = await _seed_run_without_provider_job(session)
    service = _service(session, tmp_path)
    payload = {"type": "crawl.started", "id": "crawl_race"}

    # 1. The early webhook is refused rather than silently accepted.
    with pytest.raises(WebhookRetryableError):
        await service.process_payload(payload)

    receipt = await session.scalar(select(WebhookReceipt))
    assert receipt is not None, "the delivery must be persisted for forensics"
    assert receipt.processed_at is None, (
        "an unapplied delivery must stay unprocessed, or the retry is deduped away"
    )
    await session.refresh(run)
    assert run.status is RunStatus.PENDING

    # 2. The dispatch transaction lands, so the ProviderJob now exists.
    session.add(
        ProviderJob(
            provider_job_id="pjob_race",
            run_id="run_race",
            external_job_id="crawl_race",
            status=ProviderJobStatus.ACCEPTED,
            request_payload={},
            response_payload={},
        )
    )
    await session.commit()

    # 3. Firecrawl redelivers the identical payload — it must now be applied.
    await service.process_payload(payload)

    await session.refresh(run)
    provider_job = await session.scalar(
        select(ProviderJob).where(ProviderJob.external_job_id == "crawl_race")
    )
    receipt_count = await session.scalar(select(func.count()).select_from(WebhookReceipt))
    await session.refresh(receipt)

    assert run.status is RunStatus.RUNNING
    assert provider_job is not None
    assert provider_job.status is ProviderJobStatus.RUNNING
    assert provider_job.last_event_type == "crawl.started"
    assert receipt_count == 1, "the redelivery must reclaim the receipt, not add a second"
    assert receipt.processed_at is not None


@pytest.mark.asyncio
async def test_processed_delivery_is_still_deduped_after_it_applied(
    session, tmp_path: Path
) -> None:
    """The reclaim window closes once the event is applied: a later replay is a no-op."""
    await _seed_run_without_provider_job(session)
    session.add(
        ProviderJob(
            provider_job_id="pjob_race",
            run_id="run_race",
            external_job_id="crawl_race",
            status=ProviderJobStatus.ACCEPTED,
            request_payload={},
            response_payload={},
        )
    )
    await session.commit()
    service = _service(session, tmp_path)
    payload = {"type": "crawl.started", "id": "crawl_race"}

    await service.process_payload(payload)
    first = await session.scalar(select(WebhookReceipt))
    assert first is not None
    processed_at = first.processed_at

    await service.process_payload(payload)

    await session.refresh(first)
    receipt_count = await session.scalar(select(func.count()).select_from(WebhookReceipt))
    assert receipt_count == 1
    assert first.processed_at == processed_at, "an applied delivery must not be re-applied"


@pytest.mark.asyncio
async def test_unknown_job_is_counted_and_logged_rather_than_silently_consumed(
    session, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    before = _unmatched_count("crawl.page", "unknown_job_id")
    service = _service(session, tmp_path)

    with (
        caplog.at_level(
            logging.WARNING, logger="platform_control.services.firecrawl_webhook_service"
        ),
        pytest.raises(WebhookRetryableError),
    ):
        await service.process_payload({"type": "crawl.page", "id": "crawl_ghost", "data": []})

    assert _unmatched_count("crawl.page", "unknown_job_id") == before + 1
    assert any(
        "firecrawl.webhook.unmatched" in record.message and "crawl_ghost" in record.message
        for record in caplog.records
    ), "an unmatched delivery must be observable in the logs"


@pytest.mark.asyncio
async def test_payload_without_a_job_id_is_surfaced(session, tmp_path: Path) -> None:
    before = _unmatched_count("crawl.page", "missing_job_id")
    service = _service(session, tmp_path)

    with pytest.raises(WebhookRetryableError):
        await service.process_payload({"type": "crawl.page", "data": []})

    receipt = await session.scalar(select(WebhookReceipt))
    assert receipt is not None
    assert receipt.processed_at is None
    assert _unmatched_count("crawl.page", "missing_job_id") == before + 1
