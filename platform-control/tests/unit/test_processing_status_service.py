from __future__ import annotations

from datetime import UTC, datetime

import pytest

from platform_control.domain import ProcessingStatus, RunMode, RunStatus, SourceVersionStatus
from platform_control.errors import NotFoundError
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.processing_status_update import ProcessingStatusUpdate
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.schemas.processing_status import DocumentProcessingStatusUpdatedEvent
from platform_control.services.processing_status_service import ProcessingStatusService


async def _seed_run(session) -> Run:
    session.add(Jurisdiction(jurisdiction_id="jur_ch", name="Switzerland", slug="ch"))
    session.add(
        Authority(
            authority_id="auth_zh_admin",
            jurisdiction_id="jur_ch",
            name="Zurich Administrative Court",
            slug="zh-admin-court",
        )
    )
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
        mode=RunMode.PRODUCTION,
        status=RunStatus.RUNNING,
    )
    session.add_all([source, source_version, run])
    await session.commit()
    return run


def _build_status_event(
    event_id: str,
    status: ProcessingStatus,
) -> DocumentProcessingStatusUpdatedEvent:
    return DocumentProcessingStatusUpdatedEvent(
        event_type="document.processing_status.updated",
        event_version=1,
        event_id=event_id,
        occurred_at=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
        producer="document-intelligence",
        correlation_id="run_seed",
        payload={
            "processing_manifest_id": "pm_01jq7bhgy7g0pkj4f1d03f8f8c",
            "document_id": "doc_01jq7bdptzqv3xs0c41xpw1ybg",
            "document_revision": 3,
            "provenance": {
                "tenant_id": "tenant_public",
                "corpus_id": "corpus_public_ch_federal_law",
                "scope_type": "global_public",
                "source_id": "src_seed",
                "source_version_id": "sv_seed",
                "run_id": "run_seed",
                "source_snapshot_id": "snap_01jq7a7n3nbzj6sk7v95p9frz1",
                "bundle_manifest_id": "abm_01jq7ab8x4nm7m3qz3b8e9q2fk",
            },
            "processing_version": "di_2026_03_29",
            "status": status,
            "error_code": None,
            "error_summary": None,
        },
    )


@pytest.mark.asyncio
async def test_record_status_update_is_idempotent(session) -> None:
    await _seed_run(session)
    service = ProcessingStatusService(session)
    event = _build_status_event("evt_status_1", ProcessingStatus.CANONICAL_READY)

    await service.record_document_processing_status(event)
    await service.record_document_processing_status(event)

    updates = await service.list_run_processing_status("run_seed")
    assert len(updates) == 1
    assert updates[0].event_id == "evt_status_1"
    assert updates[0].status is ProcessingStatus.CANONICAL_READY


@pytest.mark.asyncio
async def test_list_run_processing_status_raises_for_unknown_run(session) -> None:
    service = ProcessingStatusService(session)
    with pytest.raises(NotFoundError):
        await service.list_run_processing_status("run_missing")


@pytest.mark.asyncio
async def test_list_run_processing_status_orders_by_latest_first(session) -> None:
    await _seed_run(session)
    service = ProcessingStatusService(session)
    older = _build_status_event("evt_status_old", ProcessingStatus.PROCESSING)
    newer = _build_status_event("evt_status_new", ProcessingStatus.CANONICAL_READY)
    newer = newer.model_copy(update={"occurred_at": datetime(2026, 4, 2, 12, 1, tzinfo=UTC)})

    await service.record_document_processing_status(older)
    await service.record_document_processing_status(newer)

    updates = await service.list_run_processing_status("run_seed")
    assert [update.event_id for update in updates] == ["evt_status_new", "evt_status_old"]
    assert all(isinstance(update, ProcessingStatusUpdate) for update in updates)
