"""Tests for the run lifecycle timeline aggregation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from platform_control.domain import (
    ProcessingStatus,
    RunMode,
    RunStatus,
    SourceVersionStatus,
)
from platform_control.errors import NotFoundError
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.schemas.document_events import DocumentProcessedEvent
from platform_control.schemas.processing_status import DocumentProcessingStatusUpdatedEvent
from platform_control.services.processing_status_service import ProcessingStatusService
from platform_control.services.run_lifecycle_service import RunLifecycleService

RUN_ID = "run_01jq7a3s9b7j4dndd9sgv6pb9d"
SOURCE_ID = "src_01jq79xv3wdd6yr8q5bn0m3zfk"
SOURCE_VERSION_ID = "sv_01jq79zcskf4m3m4gm3t5s59xq"


async def _seed_run(session, *, completed: bool = False) -> Run:
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
        source_id=SOURCE_ID,
        name="Zurich decisions",
        jurisdiction_id="jur_ch",
        authority_id="auth_zh_admin",
    )
    source_version = SourceVersion(
        source_version_id=SOURCE_VERSION_ID,
        source_id=SOURCE_ID,
        version_label="v1",
        status=SourceVersionStatus.APPROVED,
        acquisition_spec={"seed_url": "https://example.com/decisions", "mode": "crawl"},
    )
    run = Run(
        run_id=RUN_ID,
        source_id=SOURCE_ID,
        source_version_id=SOURCE_VERSION_ID,
        mode=RunMode.PRODUCTION,
        status=RunStatus.COMPLETED if completed else RunStatus.RUNNING,
        started_at=datetime(2026, 4, 2, 11, 0, tzinfo=UTC),
        completed_at=datetime(2026, 4, 2, 13, 0, tzinfo=UTC) if completed else None,
    )
    session.add_all([source, source_version, run])
    await session.commit()
    return run


def _build_status_event(
    event_id: str, status: ProcessingStatus
) -> DocumentProcessingStatusUpdatedEvent:
    return DocumentProcessingStatusUpdatedEvent(
        event_type="document.processing_status.updated",
        event_version=1,
        event_id=event_id,
        occurred_at=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
        producer="document-intelligence",
        correlation_id=RUN_ID,
        payload={
            "processing_manifest_id": "pm_01jq7bhgy7g0pkj4f1d03f8f8c",
            "document_id": "doc_01jq7bdptzqv3xs0c41xpw1ybg",
            "document_revision": 3,
            "provenance": {
                "tenant_id": "tenant_public",
                "corpus_id": "corpus_public_ch_federal_law",
                "scope_type": "global_public",
                "source_id": SOURCE_ID,
                "source_version_id": SOURCE_VERSION_ID,
                "run_id": RUN_ID,
                "source_snapshot_id": "snap_01jq7a7n3nbzj6sk7v95p9frz1",
                "bundle_manifest_id": "abm_01jq7ab8x4nm7m3qz3b8e9q2fk",
            },
            "processing_version": "di_2026_03_29",
            "status": status,
            "error_code": None,
            "error_summary": None,
        },
    )


def _build_document_processed_event(event_id: str) -> DocumentProcessedEvent:
    return DocumentProcessedEvent(
        event_type="document.processed",
        event_version=1,
        event_id=event_id,
        occurred_at=datetime(2026, 4, 2, 12, 2, tzinfo=UTC),
        producer="document-intelligence",
        correlation_id=RUN_ID,
        payload={
            "document_id": "doc_01jq7bdptzqv3xs0c41xpw1ybg",
            "document_revision": 3,
            "processing_manifest_id": "pm_01jq7bhgy7g0pkj4f1d03f8f8c",
            "processing_version": "di_2026_03_29",
            "provenance": {
                "tenant_id": "tenant_public",
                "corpus_id": "corpus_public_ch_federal_law",
                "scope_type": "global_public",
                "source_id": SOURCE_ID,
                "source_version_id": SOURCE_VERSION_ID,
                "run_id": RUN_ID,
                "source_snapshot_id": "snap_01jq7a7n3nbzj6sk7v95p9frz1",
                "bundle_manifest_id": "abm_01jq7ab8x4nm7m3qz3b8e9q2fk",
            },
            "lifecycle_status": "active",
            "published_document_ref": {"surface_name": "published_documents", "surface_version": 1},
            "published_sections_ref": {"surface_name": "published_sections", "surface_version": 1},
            "processing_manifest_ref": {
                "manifest_id": "pm_01jq7bhgy7g0pkj4f1d03f8f8c",
                "manifest_type": "processing_manifest",
                "manifest_version": 1,
                "dataset_ref": {"surface_name": "processing_manifests", "surface_version": 1},
            },
            "supersedes_processing_manifest_id": None,
        },
    )


@pytest.mark.asyncio
async def test_lifecycle_raises_for_unknown_run(session) -> None:
    service = RunLifecycleService(session)
    with pytest.raises(NotFoundError):
        await service.get_lifecycle("run_does_not_exist_at_all")


@pytest.mark.asyncio
async def test_lifecycle_empty_run_returns_run_entry_only(session) -> None:
    await _seed_run(session)
    service = RunLifecycleService(session)
    result = await service.get_lifecycle(RUN_ID)

    assert result.run_id == RUN_ID
    assert result.run_status == "running"
    assert result.counts.processing_status_updates == 0
    assert result.counts.document_lifecycle_events == 0
    assert len(result.timeline) == 1  # just the run-start entry
    assert result.timeline[0].kind == "run"


@pytest.mark.asyncio
async def test_lifecycle_completed_run_has_two_run_entries(session) -> None:
    await _seed_run(session, completed=True)
    service = RunLifecycleService(session)
    result = await service.get_lifecycle(RUN_ID)

    run_entries = [e for e in result.timeline if e.kind == "run"]
    assert len(run_entries) == 2  # start + completion


@pytest.mark.asyncio
async def test_lifecycle_aggregates_all_event_types(session) -> None:
    await _seed_run(session)

    # Record some DI events
    pss = ProcessingStatusService(session)
    await pss.record_document_processing_status(
        _build_status_event("evt_status_1", ProcessingStatus.ACCEPTED)
    )
    evt2 = _build_status_event("evt_status_2", ProcessingStatus.CANONICAL_READY).model_copy(
        update={
            "event_id": "evt_status_2",
            "occurred_at": datetime(2026, 4, 2, 12, 1, tzinfo=UTC),
        }
    )
    await pss.record_document_processing_status(evt2)
    await pss.record_document_processed(_build_document_processed_event("evt_processed_1"))

    service = RunLifecycleService(session)
    result = await service.get_lifecycle(RUN_ID)

    assert result.counts.processing_status_updates == 2
    assert result.counts.document_lifecycle_events == 1
    # 1 run entry + 2 status + 1 lifecycle = 4
    assert len(result.timeline) == 4


@pytest.mark.asyncio
async def test_lifecycle_timeline_is_chronologically_sorted(session) -> None:
    await _seed_run(session)

    pss = ProcessingStatusService(session)
    # Insert events with specific timestamps
    await pss.record_document_processing_status(
        _build_status_event("evt_older", ProcessingStatus.ACCEPTED)
    )
    later_event = _build_status_event("evt_newer", ProcessingStatus.CANONICAL_READY)
    later_event = later_event.model_copy(
        update={"event_id": "evt_newer", "occurred_at": datetime(2026, 4, 2, 12, 5, tzinfo=UTC)}
    )
    await pss.record_document_processing_status(later_event)

    service = RunLifecycleService(session)
    result = await service.get_lifecycle(RUN_ID)

    timestamps = [e.occurred_at for e in result.timeline]
    assert timestamps == sorted(timestamps)
