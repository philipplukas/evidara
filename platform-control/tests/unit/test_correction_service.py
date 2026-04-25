"""Unit tests for CorrectionService — lifecycle state machine + overlay sync.

Exercises the service against a SQLite-backed in-memory session via the
shared `session` fixture. Postgres-only behaviour (e.g. row locking) is
not exercised here; the integration test covers that.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.errors import (
    ConflictError,
    InvalidStateTransitionError,
    NotFoundError,
)
from platform_control.models.commentary_insight import CommentaryInsight
from platform_control.schemas.correction import (
    CorrectionStatus,
    CorrectionType,
    CreateCorrectionRequest,
    TargetEntityType,
    UpdateCorrectionStatusRequest,
)
from platform_control.services.correction_service import CorrectionService

_INSIGHT_ID = "ins_01jq7c1ny0ffv8qdr1xwbejqb6"
_OPERATOR = "op_01jqs7p1bcvz2tw5kxh9mq80fg"


def _seed_insight(session: AsyncSession) -> CommentaryInsight:
    insight = CommentaryInsight(
        insight_id=_INSIGHT_ID,
        document_id="doc_01jq7bdptzqv3xs0c41xpw1ybg",
        document_revision=3,
        processing_manifest_id="pm_01jq7bhgy7g0pkj4f1d03f8f8c",
        section_id=None,
        citation_id=None,
        insight_type="referenced_provision",
        claim="References Art. 754 OR",
        display_text="…Lehre als Haftungsnorm…",
        language="de",
        jurisdiction_id="jur_ch_federal",
        confidence=0.78,
        review_state="machine_verified",
        support=[{"document_id": "doc_01jq7bdptzqv3xs0c41xpw1ybg", "ref_type": "passage"}],
        referenced_authorities=[],
        jurisdiction_ids=["jur_ch_federal"],
        authority_ids=["auth_fedlex"],
        source_document_ids=["doc_01jq7bdptzqv3xs0c41xpw1ybg"],
        generator={"name": "extractor", "version": "v1"},
        scores={"passage_present": 1.0},
        metadata_json=None,
        overlay_revision=1,
        last_correction_id=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(insight)
    return insight


@pytest.mark.asyncio
async def test_create_pending_correction_against_existing_insight(
    session: AsyncSession,
) -> None:
    _seed_insight(session)
    await session.flush()

    service = CorrectionService(session)
    req = CreateCorrectionRequest(
        target_entity_type=TargetEntityType.COMMENTARY_INSIGHT,
        target_entity_id=_INSIGHT_ID,
        correction_type=CorrectionType.FIELD_EDIT,
        payload={"field": "claim", "value": "Sharper restated claim."},
        original_snapshot={"claim": "References Art. 754 OR"},
        rationale="Editor sharpened the claim.",
    )
    correction = await service.create(req, operator_id=_OPERATOR)

    assert correction.correction_id.startswith("cor_")
    assert correction.status == CorrectionStatus.PENDING.value
    assert correction.applied_at is None
    assert correction.operator_id == _OPERATOR


@pytest.mark.asyncio
async def test_create_against_missing_commentary_insight_404s(
    session: AsyncSession,
) -> None:
    service = CorrectionService(session)
    # Crockford-base32 ULID with no real referent in the DB.
    req = CreateCorrectionRequest(
        target_entity_type=TargetEntityType.COMMENTARY_INSIGHT,
        target_entity_id="ins_00zz0z0z0z0z0z0z0z0z0z0z00",
        correction_type=CorrectionType.FIELD_EDIT,
        payload={"field": "claim", "value": "x"},
    )
    with pytest.raises(NotFoundError):
        await service.create(req, operator_id=_OPERATOR)


@pytest.mark.asyncio
async def test_apply_field_edit_mutates_overlay_and_bumps_revision(
    session: AsyncSession,
) -> None:
    insight = _seed_insight(session)
    await session.flush()

    service = CorrectionService(session)
    correction = await service.create(
        CreateCorrectionRequest(
            target_entity_type=TargetEntityType.COMMENTARY_INSIGHT,
            target_entity_id=_INSIGHT_ID,
            correction_type=CorrectionType.FIELD_EDIT,
            payload={"field": "claim", "value": "Sharpened claim text."},
            original_snapshot={"claim": "References Art. 754 OR"},
        ),
        operator_id=_OPERATOR,
    )

    applied = await service.update_status(
        correction.correction_id,
        UpdateCorrectionStatusRequest(status=CorrectionStatus.APPLIED),
    )

    await session.refresh(insight)
    assert applied.status == CorrectionStatus.APPLIED.value
    assert applied.applied_at is not None
    assert insight.claim == "Sharpened claim text."
    assert insight.overlay_revision == 2
    assert insight.last_correction_id == correction.correction_id


@pytest.mark.asyncio
async def test_reject_marks_overlay_review_state_and_bumps_revision(
    session: AsyncSession,
) -> None:
    insight = _seed_insight(session)
    await session.flush()

    service = CorrectionService(session)
    correction = await service.create(
        CreateCorrectionRequest(
            target_entity_type=TargetEntityType.COMMENTARY_INSIGHT,
            target_entity_id=_INSIGHT_ID,
            correction_type=CorrectionType.REJECT,
            payload={"reason": "garbled extraction"},
        ),
        operator_id=_OPERATOR,
    )
    await service.update_status(
        correction.correction_id,
        UpdateCorrectionStatusRequest(status=CorrectionStatus.APPLIED),
    )

    await session.refresh(insight)
    assert insight.review_state == "rejected"
    assert insight.overlay_revision == 2


@pytest.mark.asyncio
async def test_annotation_does_not_mutate_overlay_but_bumps_revision(
    session: AsyncSession,
) -> None:
    """Audit-only types (annotation, rescore_request) still bump the
    overlay revision so a UI can render `n corrections applied` even
    when the field set is untouched."""

    insight = _seed_insight(session)
    await session.flush()

    service = CorrectionService(session)
    correction = await service.create(
        CreateCorrectionRequest(
            target_entity_type=TargetEntityType.COMMENTARY_INSIGHT,
            target_entity_id=_INSIGHT_ID,
            correction_type=CorrectionType.ANNOTATION,
            payload={"note": "double-check"},
        ),
        operator_id=_OPERATOR,
    )
    await service.update_status(
        correction.correction_id,
        UpdateCorrectionStatusRequest(status=CorrectionStatus.APPLIED),
    )

    await session.refresh(insight)
    assert insight.review_state == "machine_verified"  # unchanged
    assert insight.claim == "References Art. 754 OR"  # unchanged
    assert insight.overlay_revision == 2


@pytest.mark.asyncio
async def test_rejects_illegal_status_transition_pending_to_superseded(
    session: AsyncSession,
) -> None:
    _seed_insight(session)
    await session.flush()

    service = CorrectionService(session)
    correction = await service.create(
        CreateCorrectionRequest(
            target_entity_type=TargetEntityType.COMMENTARY_INSIGHT,
            target_entity_id=_INSIGHT_ID,
            correction_type=CorrectionType.FIELD_EDIT,
            payload={"field": "claim", "value": "x"},
        ),
        operator_id=_OPERATOR,
    )

    with pytest.raises(InvalidStateTransitionError, match="Illegal correction status"):
        await service.update_status(
            correction.correction_id,
            UpdateCorrectionStatusRequest(status=CorrectionStatus.SUPERSEDED),
        )


@pytest.mark.asyncio
async def test_field_edit_on_non_editable_field_raises_conflict(
    session: AsyncSession,
) -> None:
    """`overlay_revision`, `insight_id`, etc. must not be editable."""

    _seed_insight(session)
    await session.flush()

    service = CorrectionService(session)
    correction = await service.create(
        CreateCorrectionRequest(
            target_entity_type=TargetEntityType.COMMENTARY_INSIGHT,
            target_entity_id=_INSIGHT_ID,
            correction_type=CorrectionType.FIELD_EDIT,
            payload={"field": "overlay_revision", "value": 999},
        ),
        operator_id=_OPERATOR,
    )

    with pytest.raises(ConflictError, match="not permitted"):
        await service.update_status(
            correction.correction_id,
            UpdateCorrectionStatusRequest(status=CorrectionStatus.APPLIED),
        )


@pytest.mark.asyncio
async def test_applied_can_transition_to_superseded(session: AsyncSession) -> None:
    _seed_insight(session)
    await session.flush()

    service = CorrectionService(session)
    correction = await service.create(
        CreateCorrectionRequest(
            target_entity_type=TargetEntityType.COMMENTARY_INSIGHT,
            target_entity_id=_INSIGHT_ID,
            correction_type=CorrectionType.FIELD_EDIT,
            payload={"field": "claim", "value": "v1"},
        ),
        operator_id=_OPERATOR,
    )
    await service.update_status(
        correction.correction_id,
        UpdateCorrectionStatusRequest(status=CorrectionStatus.APPLIED),
    )
    superseded = await service.update_status(
        correction.correction_id,
        UpdateCorrectionStatusRequest(status=CorrectionStatus.SUPERSEDED),
    )
    assert superseded.status == CorrectionStatus.SUPERSEDED.value


@pytest.mark.asyncio
async def test_list_filters_combine(session: AsyncSession) -> None:
    _seed_insight(session)
    await session.flush()

    service = CorrectionService(session)
    for _ in range(3):
        await service.create(
            CreateCorrectionRequest(
                target_entity_type=TargetEntityType.COMMENTARY_INSIGHT,
                target_entity_id=_INSIGHT_ID,
                correction_type=CorrectionType.FIELD_EDIT,
                payload={"field": "claim", "value": "x"},
            ),
            operator_id=_OPERATOR,
        )

    rows, total = await service.list(
        target_entity_type=TargetEntityType.COMMENTARY_INSIGHT,
        target_entity_id=_INSIGHT_ID,
        status=CorrectionStatus.PENDING,
        limit=10,
        offset=0,
    )
    assert total == 3
    assert len(rows) == 3
