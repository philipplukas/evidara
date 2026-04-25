"""Unit tests for the correction schema validation.

Mirror the conditional `target_entity_id` rules from
`contracts/schemas/corrections.json` and the lifecycle invariants
enforced in `UpdateCorrectionStatusRequest`.
"""

from __future__ import annotations

import pytest

from platform_control.schemas.correction import (
    CorrectionStatus,
    CorrectionType,
    CreateCorrectionRequest,
    TargetEntityType,
    UpdateCorrectionStatusRequest,
)


class TestCreateCorrectionRequest:
    def test_accepts_commentary_insight_target(self) -> None:
        req = CreateCorrectionRequest(
            target_entity_type=TargetEntityType.COMMENTARY_INSIGHT,
            target_entity_id="ins_01jq7c1ny0ffv8qdr1xwbejqb6",
            correction_type=CorrectionType.FIELD_EDIT,
            payload={"field": "claim", "value": "test"},
        )
        assert req.target_entity_id == "ins_01jq7c1ny0ffv8qdr1xwbejqb6"

    def test_accepts_document_target(self) -> None:
        req = CreateCorrectionRequest(
            target_entity_type=TargetEntityType.DOCUMENT,
            target_entity_id="doc_01jq7bdptzqv3xs0c41xpw1ybg",
            correction_type=CorrectionType.RESCORE_REQUEST,
            payload={"reason_code": "low_quality"},
        )
        assert req.target_entity_id == "doc_01jq7bdptzqv3xs0c41xpw1ybg"

    def test_accepts_source_target(self) -> None:
        req = CreateCorrectionRequest(
            target_entity_type=TargetEntityType.SOURCE,
            target_entity_id="src_abc123",
            correction_type=CorrectionType.ANNOTATION,
            payload={"note": "review later"},
        )
        assert req.target_entity_id == "src_abc123"

    def test_rejects_target_id_pattern_mismatch(self) -> None:
        with pytest.raises(ValueError, match="does not match the pattern"):
            CreateCorrectionRequest(
                target_entity_type=TargetEntityType.COMMENTARY_INSIGHT,
                target_entity_id="doc_01jq7bdptzqv3xs0c41xpw1ybg",
                correction_type=CorrectionType.FIELD_EDIT,
                payload={"field": "claim", "value": "test"},
            )

    def test_rejects_unknown_extra_fields(self) -> None:
        with pytest.raises(ValueError):
            CreateCorrectionRequest(
                target_entity_type=TargetEntityType.SOURCE,
                target_entity_id="src_abc123",
                correction_type=CorrectionType.ANNOTATION,
                payload={"note": "x"},
                operator_id="op_should_not_be_in_request",  # type: ignore[call-arg]
            )

    def test_rationale_max_length(self) -> None:
        with pytest.raises(ValueError):
            CreateCorrectionRequest(
                target_entity_type=TargetEntityType.SOURCE,
                target_entity_id="src_abc123",
                correction_type=CorrectionType.ANNOTATION,
                payload={"note": "x"},
                rationale="x" * 2001,
            )


class TestUpdateCorrectionStatusRequest:
    @pytest.mark.parametrize(
        "target",
        [
            CorrectionStatus.APPLIED,
            CorrectionStatus.REJECTED,
            CorrectionStatus.SUPERSEDED,
        ],
    )
    def test_accepts_terminal_targets(self, target: CorrectionStatus) -> None:
        req = UpdateCorrectionStatusRequest(status=target)
        assert req.status is target

    def test_rejects_pending_target(self) -> None:
        with pytest.raises(
            ValueError,
            match="Cannot transition correction status back to 'pending'",
        ):
            UpdateCorrectionStatusRequest(status=CorrectionStatus.PENDING)
