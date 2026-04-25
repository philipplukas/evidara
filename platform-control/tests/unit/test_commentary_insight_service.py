from __future__ import annotations

import pytest

from platform_control.domain import (
    CommentaryInsightReviewState,
    CorrectionStatus,
    CorrectionTargetEntityType,
    CorrectionType,
)
from platform_control.errors import ConflictError, NotFoundError
from platform_control.models.commentary_insight import CommentaryInsight
from platform_control.schemas.commentary_insight import PatchCommentaryInsightRequest
from platform_control.services.commentary_insight_service import (
    CommentaryInsightService,
)
from platform_control.services.correction_service import CorrectionService


def _seed_insight(**overrides):
    base = dict(
        insight_id="ins_01h8x7m6q9n8r2v5y0a3b1c4d6",
        document_id="doc_01h8x7m6q9n8r2v5y0a3b1c4xx",
        document_revision=1,
        processing_manifest_id="pm_01h8x7m6q9n8r2v5y0a3b1c4yy",
        section_id=None,
        citation_id=None,
        insight_type="commentary_anchor",
        claim="Initial claim text.",
        display_text="Initial display passage.",
        support=[{"snippet": "init"}],
        referenced_authorities=[],
        language="en",
        jurisdiction_id="jur_ch",
        authority_id=None,
        confidence=0.8,
        review_state=CommentaryInsightReviewState.MACHINE_GENERATED_UNREVIEWED,
        generator={"name": "di", "version": "0.1"},
        scores={
            "passage_present": 1.0,
            "citation_parseable": 1.0,
            "section_anchor_resolved": 0.0,
        },
    )
    base.update(overrides)
    return CommentaryInsight(**base)


@pytest.mark.asyncio
async def test_apply_field_edit_writes_correction_and_bumps_version(session) -> None:
    insight = _seed_insight()
    session.add(insight)
    await session.commit()

    service = CommentaryInsightService(session)
    patched = await service.apply_field_edit(
        insight.insight_id,
        PatchCommentaryInsightRequest(
            operator_id="op_alice",
            rationale="copy fix",
            patch={"claim": "Updated claim text."},
            original_snapshot={"claim": "Initial claim text."},
        ),
    )

    assert patched.claim == "Updated claim text."
    assert patched.current_version == 2
    assert patched.last_correction_id is not None

    # Audit row was created and applied.
    correction_service = CorrectionService(session)
    history = await correction_service.list_history_for_entity(
        target_entity_type=CorrectionTargetEntityType.COMMENTARY_INSIGHT,
        target_entity_id=insight.insight_id,
    )
    assert len(history) == 1
    row = history[0]
    assert row.correction_type == CorrectionType.FIELD_EDIT
    assert row.status == CorrectionStatus.APPLIED
    assert row.applied_at is not None
    assert row.payload == {"claim": "Updated claim text."}
    assert row.original_snapshot == {"claim": "Initial claim text."}


@pytest.mark.asyncio
async def test_apply_field_edit_rejects_stale_snapshot(session) -> None:
    insight = _seed_insight()
    session.add(insight)
    await session.commit()

    service = CommentaryInsightService(session)
    with pytest.raises(ConflictError):
        await service.apply_field_edit(
            insight.insight_id,
            PatchCommentaryInsightRequest(
                operator_id="op_alice",
                patch={"claim": "Updated claim text."},
                # Snapshot does not match the persisted value.
                original_snapshot={"claim": "Something the operator never saw."},
            ),
        )


@pytest.mark.asyncio
async def test_apply_field_edit_can_change_review_state(session) -> None:
    insight = _seed_insight()
    session.add(insight)
    await session.commit()

    service = CommentaryInsightService(session)
    patched = await service.apply_field_edit(
        insight.insight_id,
        PatchCommentaryInsightRequest(
            operator_id="op_alice",
            patch={"review_state": "editor_approved"},
            original_snapshot={"review_state": "machine_generated_unreviewed"},
        ),
    )
    assert patched.review_state == CommentaryInsightReviewState.EDITOR_APPROVED


@pytest.mark.asyncio
async def test_get_unknown_insight_raises_not_found(session) -> None:
    service = CommentaryInsightService(session)
    with pytest.raises(NotFoundError):
        await service.get_insight("ins_doesnotexist")


@pytest.mark.asyncio
async def test_correction_queue_filters_by_status_and_type(session) -> None:
    insight = _seed_insight()
    session.add(insight)
    await session.commit()

    service = CommentaryInsightService(session)
    await service.apply_field_edit(
        insight.insight_id,
        PatchCommentaryInsightRequest(
            operator_id="op_alice",
            patch={"claim": "v2"},
            original_snapshot={"claim": "Initial claim text."},
        ),
    )

    correction_service = CorrectionService(session)
    pending = await correction_service.list_queue(status=CorrectionStatus.PENDING)
    applied = await correction_service.list_queue(status=CorrectionStatus.APPLIED)
    assert pending == []
    assert len(applied) == 1


@pytest.mark.asyncio
async def test_patch_request_rejects_unknown_field() -> None:
    with pytest.raises(ValueError):
        PatchCommentaryInsightRequest(
            operator_id="op_alice",
            patch={"document_id": "doc_other"},
            original_snapshot={"document_id": "doc_old"},
        )


@pytest.mark.asyncio
async def test_patch_request_requires_snapshot_per_patched_field() -> None:
    with pytest.raises(ValueError):
        PatchCommentaryInsightRequest(
            operator_id="op_alice",
            patch={"claim": "x", "display_text": "y"},
            original_snapshot={"claim": "before"},
        )


@pytest.mark.asyncio
async def test_patch_request_requires_at_least_one_field() -> None:
    with pytest.raises(ValueError):
        PatchCommentaryInsightRequest(
            operator_id="op_alice",
            patch={},
            original_snapshot={},
        )
