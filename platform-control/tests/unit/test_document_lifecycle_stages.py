"""The DI stage ledger survives the crossing into platform-control (#903).

document-intelligence records what each pipeline stage did and denormalises it
onto `document.processed`. These tests cover the receiving half: that it is
stored, that it is served, and — the part that carries the honesty rule — that
"no ledger" stays distinguishable from "the pipeline ran no stages".
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from test_processing_status_service import (  # noqa: F401 - shared fixtures
    RUN_ID,
    _build_document_processed_event,
    _seed_run,
)

from platform_control.models.document_lifecycle_event import DocumentLifecycleEvent
from platform_control.schemas.document_events import (
    DocumentLifecycleEventResponse,
    DocumentProcessedEvent,
)
from platform_control.services.processing_status_service import ProcessingStatusService

STAGES = [
    {"name": "normalize", "duration_ms": 120, "items_in": 1, "items_out": 1},
    {"name": "sectionize", "duration_ms": 45, "items_in": 1, "items_out": 24},
    {"name": "extract", "duration_ms": 890, "items_in": 1, "items_out": 1},
    {"name": "assemble", "duration_ms": 12, "items_in": 1, "items_out": 1},
    {"name": "enrich", "duration_ms": 310, "items_in": 24, "items_out": 7},
    {"name": "finalize", "duration_ms": 8, "items_in": 24, "items_out": 24},
]


def _event_with_stages(event_id: str, stages: list[dict] | None) -> DocumentProcessedEvent:
    base = _build_document_processed_event(event_id)
    payload = base.payload.model_dump()
    if stages is not None:
        payload["stages"] = stages
    else:
        payload.pop("stages", None)
    return DocumentProcessedEvent(**{**base.model_dump(exclude={"payload"}), "payload": payload})


async def _stored_row(session) -> DocumentLifecycleEvent:
    return await session.scalar(
        select(DocumentLifecycleEvent).where(DocumentLifecycleEvent.run_id == RUN_ID)
    )


@pytest.mark.asyncio
async def test_stages_are_stored_in_order_with_their_counts(session) -> None:
    await _seed_run(session)
    service = ProcessingStatusService(session)

    await service.record_document_processed(_event_with_stages("evt_stages_1", STAGES))

    row = await _stored_row(session)
    assert [stage["name"] for stage in row.stages] == [stage["name"] for stage in STAGES]
    sectionize = next(s for s in row.stages if s["name"] == "sectionize")
    assert sectionize["items_out"] == 24
    assert sectionize["duration_ms"] == 45


@pytest.mark.asyncio
async def test_a_producer_that_sends_no_ledger_stores_null_not_an_empty_list(session) -> None:
    """The load-bearing case.

    `[]` is a claim that the pipeline ran no stages. NULL is "we recorded none".
    Every row written before #903 is NULL, and every event from an older
    document-intelligence produces NULL. Collapsing the two would turn "never
    recorded" into "nothing happened" — the silent-zero failure this repo has
    already paid for in #605, #675 and #713.

    Change `_stages_for_storage` to return `[]` instead of `None` and this fails.
    """
    await _seed_run(session)
    service = ProcessingStatusService(session)

    await service.record_document_processed(_event_with_stages("evt_stages_absent", None))

    row = await _stored_row(session)
    assert row.stages is None
    assert row.stages != []


@pytest.mark.asyncio
async def test_an_unmeasured_count_is_omitted_rather_than_stored_as_zero(session) -> None:
    """`0 in → 0 out` is a claim about the work; a missing key is an absence."""
    await _seed_run(session)
    service = ProcessingStatusService(session)

    await service.record_document_processed(
        _event_with_stages("evt_stages_partial", [{"name": "finalize", "duration_ms": 3}])
    )

    row = await _stored_row(session)
    (stage,) = row.stages
    assert "items_in" not in stage
    assert "items_out" not in stage
    assert stage["duration_ms"] == 3


@pytest.mark.asyncio
async def test_a_failed_stage_keeps_its_error_type(session) -> None:
    await _seed_run(session)
    service = ProcessingStatusService(session)

    await service.record_document_processed(
        _event_with_stages(
            "evt_stages_failed",
            [{"name": "extract", "duration_ms": 41, "failed": True, "error_type": "ValueError"}],
        )
    )

    row = await _stored_row(session)
    (stage,) = row.stages
    assert stage["failed"] is True
    assert stage["error_type"] == "ValueError"


@pytest.mark.asyncio
async def test_the_read_model_serves_the_ledger(session) -> None:
    await _seed_run(session)
    service = ProcessingStatusService(session)
    await service.record_document_processed(_event_with_stages("evt_stages_read", STAGES))

    row = await _stored_row(session)
    response = DocumentLifecycleEventResponse.model_validate(row)

    assert response.stages is not None
    assert [stage.name for stage in response.stages] == [stage["name"] for stage in STAGES]


@pytest.mark.asyncio
async def test_the_read_model_reports_an_absent_ledger_as_none(session) -> None:
    """A client must be able to render "not recorded". Serving `[]` here would
    make that impossible.
    """
    await _seed_run(session)
    service = ProcessingStatusService(session)
    await service.record_document_processed(_event_with_stages("evt_stages_read_none", None))

    response = DocumentLifecycleEventResponse.model_validate(await _stored_row(session))

    assert response.stages is None


def test_an_unknown_stage_name_is_refused_at_the_boundary() -> None:
    """The vocabulary is closed on the wire too. A typo'd name would otherwise
    reach the admin as a row nothing can place in the timeline.
    """
    with pytest.raises(ValueError):
        _event_with_stages("evt_bad", [{"name": "preprocesss", "duration_ms": 1}])
