"""Unit tests for the correction-metrics aggregation (#432).

The aggregation runs in Python over the corrections audit log; these
tests pin the bucket math, group ordering, operator throughput
ranking, and the rescore-outcome counters (placeholder until #427).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.models.commentary_insight import CommentaryInsight
from platform_control.models.correction import Correction
from platform_control.services.correction_service import (
    CorrectionService,
    _aggregate_operator_throughput,
    _aggregate_rescore_outcomes,
    _floor_to_week_start,
)

_INSIGHT_ID = "ins_01jq7c1ny0ffv8qdr1xwbejqb6"


def _seed_insight(session: AsyncSession) -> None:
    session.add(
        CommentaryInsight(
            insight_id=_INSIGHT_ID,
            document_id="doc_01jq7bdptzqv3xs0c41xpw1ybg",
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
            support=[{"document_id": "doc_01jq7bdptzqv3xs0c41xpw1ybg", "ref_type": "passage"}],
            referenced_authorities=[],
            jurisdiction_ids=["jur_ch_federal"],
            authority_ids=["auth_fedlex"],
            source_document_ids=["doc_01jq7bdptzqv3xs0c41xpw1ybg"],
            generator={"name": "x", "version": "v1"},
            scores={},
            metadata_json=None,
            overlay_revision=1,
            last_correction_id=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )


def _make_correction(
    *,
    correction_id: str,
    correction_type: str,
    status: str,
    operator_id: str,
    created_at: datetime,
    target_entity_type: str = "commentary_insight",
    payload: dict | None = None,
) -> Correction:
    return Correction(
        correction_id=correction_id,
        target_entity_type=target_entity_type,
        target_entity_id=_INSIGHT_ID,
        correction_type=correction_type,
        payload=payload or {"field": "claim", "value": "x"},
        original_snapshot=None,
        operator_id=operator_id,
        pipeline_run_id=None,
        rationale=None,
        status=status,
        created_at=created_at,
        applied_at=None,
    )


class TestFloorToWeekStart:
    def test_monday_already_at_week_start(self) -> None:
        # 2026-04-20 is a Monday.
        result = _floor_to_week_start(datetime(2026, 4, 20, 14, 30, tzinfo=UTC))
        assert result == datetime(2026, 4, 20, 0, 0, tzinfo=UTC)

    def test_friday_floors_to_preceding_monday(self) -> None:
        # 2026-04-24 is a Friday.
        result = _floor_to_week_start(datetime(2026, 4, 24, 23, 59, tzinfo=UTC))
        assert result == datetime(2026, 4, 20, 0, 0, tzinfo=UTC)

    def test_naive_datetime_treated_as_utc(self) -> None:
        # SQLite returns naive datetimes via aiosqlite; aggregation
        # must not blow up on the missing tzinfo.
        result = _floor_to_week_start(datetime(2026, 4, 24, 23, 59))
        assert result == datetime(2026, 4, 20, 0, 0, tzinfo=UTC)


class TestOperatorThroughput:
    def test_sorts_by_total_desc_then_id_asc_and_truncates_to_top_n(self) -> None:
        rows = [
            _make_correction(
                correction_id=f"cor_{i:02d}",
                correction_type="field_edit",
                status="applied" if i % 2 == 0 else "rejected",
                operator_id=op,
                created_at=datetime(2026, 4, 20, tzinfo=UTC),
            )
            for i, op in enumerate(
                [
                    "op_a",
                    "op_a",
                    "op_a",
                    "op_b",
                    "op_b",
                    "op_c",
                ]
            )
        ]
        result = _aggregate_operator_throughput(rows, top_n=2)
        assert result == [
            {"operator_id": "op_a", "total": 3, "applied": 2, "rejected": 1},
            {"operator_id": "op_b", "total": 2, "applied": 1, "rejected": 1},
        ]

    def test_returns_empty_list_when_no_rows(self) -> None:
        assert _aggregate_operator_throughput([], top_n=10) == []


class TestRescoreOutcomes:
    def test_counts_only_rescore_request_corrections_by_status(self) -> None:
        rows = [
            _make_correction(
                correction_id="cor_field_edit",
                correction_type="field_edit",
                status="applied",
                operator_id="op_x",
                created_at=datetime(2026, 4, 20, tzinfo=UTC),
            ),
            _make_correction(
                correction_id="cor_rescore_pending",
                correction_type="rescore_request",
                status="pending",
                operator_id="op_x",
                created_at=datetime(2026, 4, 20, tzinfo=UTC),
                payload={},
            ),
            _make_correction(
                correction_id="cor_rescore_applied_changed",
                correction_type="rescore_request",
                status="applied",
                operator_id="op_x",
                created_at=datetime(2026, 4, 20, tzinfo=UTC),
                payload={"rescore_outcome": "changed"},
            ),
            _make_correction(
                correction_id="cor_rescore_rejected",
                correction_type="rescore_request",
                status="rejected",
                operator_id="op_x",
                created_at=datetime(2026, 4, 20, tzinfo=UTC),
                payload={},
            ),
        ]
        result = _aggregate_rescore_outcomes(rows)
        # `field_edit` row is excluded; `rescore_request` rows split by status.
        assert result == {
            "pending": 1,
            "applied_total": 1,
            "rejected": 1,
            "changed": 1,
            "unchanged": 0,
            "failed": 0,
        }


@pytest.mark.asyncio
async def test_get_metrics_buckets_corrections_into_weekly_series(
    session: AsyncSession,
) -> None:
    _seed_insight(session)
    await session.flush()

    now = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)  # Monday 2026-04-27
    week_starts = [now - timedelta(weeks=offset) for offset in range(8)]

    # Place one field_edit correction in each of the last 4 weeks.
    for i, week_start in enumerate(week_starts[:4]):
        session.add(
            _make_correction(
                correction_id=f"cor_we_{i:02d}",
                correction_type="field_edit",
                status="applied",
                operator_id="op_01",
                created_at=week_start + timedelta(days=2),
            )
        )

    # And two rescore_request corrections in the current week.
    for i, status in enumerate(["pending", "applied"]):
        session.add(
            _make_correction(
                correction_id=f"cor_rescore_{i:02d}",
                correction_type="rescore_request",
                status=status,
                operator_id="op_02",
                created_at=week_starts[0] + timedelta(days=1),
                payload={"rescore_outcome": "changed"} if status == "applied" else {},
            )
        )

    await session.flush()

    service = CorrectionService(session)
    metrics = await service.get_metrics(
        window_weeks=8,
        operator_throughput_window_days=30,
        operator_throughput_top_n=10,
        now=now,
    )

    assert metrics["window_weeks"] == 8
    # Two correction_types observed: field_edit + rescore_request.
    assert {s["key"] for s in metrics["weekly_by_correction_type"]} == {
        "field_edit",
        "rescore_request",
    }
    field_edit_series = next(
        s for s in metrics["weekly_by_correction_type"] if s["key"] == "field_edit"
    )
    # 8 buckets returned regardless of how many had rows.
    assert len(field_edit_series["buckets"]) == 8
    # 4 most-recent buckets each have count 1; older buckets are 0.
    counts = [b["count"] for b in field_edit_series["buckets"]]
    assert counts[-4:] == [1, 1, 1, 1]
    assert counts[:-4] == [0, 0, 0, 0]

    # Rescore outcomes pin the placeholder counters.
    assert metrics["rescore_outcomes"]["pending"] == 1
    assert metrics["rescore_outcomes"]["applied_total"] == 1
    assert metrics["rescore_outcomes"]["changed"] == 1

    # Operator throughput aggregates by operator over the window.
    operators = {entry["operator_id"]: entry for entry in metrics["operator_throughput"]}
    assert operators["op_01"]["total"] == 4
    assert operators["op_02"]["total"] == 2


@pytest.mark.asyncio
async def test_get_metrics_returns_empty_series_when_no_corrections(
    session: AsyncSession,
) -> None:
    service = CorrectionService(session)
    metrics = await service.get_metrics(
        window_weeks=4,
        operator_throughput_window_days=14,
        now=datetime(2026, 4, 27, 12, 0, tzinfo=UTC),
    )
    assert metrics["weekly_by_target_entity_type"] == []
    assert metrics["weekly_by_correction_type"] == []
    assert metrics["operator_throughput"] == []
    assert metrics["rescore_outcomes"] == {
        "pending": 0,
        "applied_total": 0,
        "rejected": 0,
        "changed": 0,
        "unchanged": 0,
        "failed": 0,
    }


@pytest.mark.asyncio
async def test_get_metrics_window_validation(session: AsyncSession) -> None:
    service = CorrectionService(session)
    with pytest.raises(ValueError, match="window_weeks"):
        await service.get_metrics(window_weeks=0)
    with pytest.raises(ValueError, match="operator_throughput_window_days"):
        await service.get_metrics(window_weeks=4, operator_throughput_window_days=0)
