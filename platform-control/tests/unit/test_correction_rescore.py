"""Unit tests for the rescore-from-correction service hook (#427).

Pins the validation rules, the idempotent re-fire behaviour, and the
outcome-recording flow that the metrics widget reads. The Temporal
workflow itself is exercised at a higher level (the activity's
`record_rescore_outcome` call is what these tests cover).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.errors import ConflictError
from platform_control.models.commentary_insight import CommentaryInsight
from platform_control.schemas.correction import (
    CorrectionStatus,
    CorrectionType,
    CreateCorrectionRequest,
    TargetEntityType,
    UpdateCorrectionStatusRequest,
)
from platform_control.services.correction_service import CorrectionService
from platform_control.services.rescore_scheduler import (
    InMemoryRescoreScheduler,
    rescore_workflow_id,
)

_INSIGHT_ID = "ins_01jq7c1ny0ffv8qdr1xwbejqb6"
_DOCUMENT_ID = "doc_01jq7bdptzqv3xs0c41xpw1ybg"
_OPERATOR = "op_01jqs7p1bcvz2tw5kxh9mq80fg"


def _seed_insight(session: AsyncSession) -> None:
    session.add(
        CommentaryInsight(
            insight_id=_INSIGHT_ID,
            document_id=_DOCUMENT_ID,
            document_revision=1,
            processing_manifest_id="pm_01jq7bhgy7g0pkj4f1d03f8f8c",
            section_id=None,
            citation_id=None,
            insight_type="referenced_provision",
            claim="x",
            display_text="x",
            language=None,
            jurisdiction_id=None,
            confidence=0.5,
            review_state="machine_verified",
            support=[{"document_id": _DOCUMENT_ID, "ref_type": "passage"}],
            referenced_authorities=[],
            jurisdiction_ids=["jur_ch_federal"],
            authority_ids=["auth_fedlex"],
            source_document_ids=[_DOCUMENT_ID],
            generator={"name": "x", "version": "v1"},
            scores={},
            metadata_json=None,
            overlay_revision=1,
            last_correction_id=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )


async def _make_rescore_correction(session: AsyncSession) -> str:
    service = CorrectionService(session)
    correction = await service.create(
        CreateCorrectionRequest(
            target_entity_type=TargetEntityType.DOCUMENT,
            target_entity_id=_DOCUMENT_ID,
            correction_type=CorrectionType.RESCORE_REQUEST,
            payload={"reason_code": "low_quality_extractions"},
        ),
        operator_id=_OPERATOR,
    )
    return correction.correction_id


@pytest.mark.asyncio
async def test_trigger_rescore_schedules_workflow_and_records_handle_on_payload(
    session: AsyncSession,
) -> None:
    correction_id = await _make_rescore_correction(session)
    scheduler = InMemoryRescoreScheduler()
    service = CorrectionService(session)

    result = await service.trigger_rescore(correction_id, scheduler=scheduler)

    assert result["correction_id"] == correction_id
    assert result["workflow_id"] == rescore_workflow_id(correction_id)
    assert result["already_running"] is False
    assert result["triggered_at"] is not None

    # Scheduler saw the call once with the right shape.
    assert len(scheduler.triggered) == 1
    call = scheduler.triggered[0]
    assert call["correction_id"] == correction_id
    assert call["target_entity_type"] == TargetEntityType.DOCUMENT.value
    assert call["target_entity_id"] == _DOCUMENT_ID

    # Correction payload now carries the workflow handle hint.
    refreshed = await service.get(correction_id)
    assert refreshed.payload["triggered_workflow_id"] == rescore_workflow_id(correction_id)
    assert refreshed.payload["triggered_at"] is not None


@pytest.mark.asyncio
async def test_trigger_rescore_is_idempotent_does_not_reschedule(
    session: AsyncSession,
) -> None:
    correction_id = await _make_rescore_correction(session)
    scheduler = InMemoryRescoreScheduler()
    service = CorrectionService(session)

    await service.trigger_rescore(correction_id, scheduler=scheduler)
    second = await service.trigger_rescore(correction_id, scheduler=scheduler)

    assert second["already_running"] is True
    assert second["workflow_id"] == rescore_workflow_id(correction_id)
    # Scheduler.schedule was only called once — second trigger short-circuits.
    assert len(scheduler.triggered) == 1


@pytest.mark.asyncio
async def test_trigger_rescore_rejects_non_rescore_correction(
    session: AsyncSession,
) -> None:
    _seed_insight(session)
    await session.flush()
    service = CorrectionService(session)
    field_edit = await service.create(
        CreateCorrectionRequest(
            target_entity_type=TargetEntityType.COMMENTARY_INSIGHT,
            target_entity_id=_INSIGHT_ID,
            correction_type=CorrectionType.FIELD_EDIT,
            payload={"field": "claim", "value": "x"},
        ),
        operator_id=_OPERATOR,
    )
    scheduler = InMemoryRescoreScheduler()

    with pytest.raises(ConflictError, match="rescore_request"):
        await service.trigger_rescore(field_edit.correction_id, scheduler=scheduler)
    assert scheduler.triggered == []


@pytest.mark.asyncio
async def test_trigger_rescore_rejects_terminal_status(session: AsyncSession) -> None:
    correction_id = await _make_rescore_correction(session)
    service = CorrectionService(session)
    await service.update_status(
        correction_id,
        UpdateCorrectionStatusRequest(status=CorrectionStatus.REJECTED),
    )
    scheduler = InMemoryRescoreScheduler()

    with pytest.raises(ConflictError, match="status"):
        await service.trigger_rescore(correction_id, scheduler=scheduler)
    assert scheduler.triggered == []


@pytest.mark.asyncio
async def test_record_rescore_outcome_writes_payload(session: AsyncSession) -> None:
    correction_id = await _make_rescore_correction(session)
    service = CorrectionService(session)

    updated = await service.record_rescore_outcome(
        correction_id, outcome="changed", resulting_run_id="run_01jq7a3s9b7j4dndd9sgv6pb9d"
    )

    assert updated.payload["rescore_outcome"] == "changed"
    assert updated.payload["resulting_run_id"] == "run_01jq7a3s9b7j4dndd9sgv6pb9d"
    assert updated.payload["completed_at"] is not None


@pytest.mark.asyncio
async def test_record_rescore_outcome_validates_outcome_value(
    session: AsyncSession,
) -> None:
    correction_id = await _make_rescore_correction(session)
    service = CorrectionService(session)

    with pytest.raises(ValueError, match="outcome"):
        await service.record_rescore_outcome(correction_id, outcome="weird")
