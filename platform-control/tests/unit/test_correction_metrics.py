"""Unit coverage for ``CorrectionService.get_metrics`` (#432).

The metrics endpoint is the HITL-moat dashboard's only data source: every
week-bucket card on the admin widget reads off this aggregator. These
tests pin the bucketing rules so a future refactor can't silently change
the dashboard's read-model:

* week_start is always the Monday of the ISO week containing created_at,
  irrespective of input timezone;
* by_entity_type and by_correction_type sum every row in the bucket;
* operator_throughput only counts ``applied`` operator corrections (no
  rescore_request rows, no nulls);
* rescore_outcomes only counts terminal CHANGED / UNCHANGED / FAILED rows
  (TRIGGERED / PENDING are excluded — the issue specifies "rescore
  outcomes", not "rescore queue").

Tests run against the SQLite-backed ``session_maker`` fixture from the
top-level conftest, which mirrors how the rest of the platform-control
unit suite exercises async-SQLA code.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_control.domain import (
    CorrectionStatus,
    CorrectionTargetEntityType,
    CorrectionType,
)
from platform_control.models.correction import Correction
from platform_control.services.correction_service import (
    DEFAULT_METRICS_LOOKBACK_WEEKS,
    CorrectionService,
    _iso_week_start,
)


async def _insert(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    created_at: datetime,
    correction_type: CorrectionType = CorrectionType.FIELD_EDIT,
    target_entity_type: CorrectionTargetEntityType = CorrectionTargetEntityType.COMMENTARY_INSIGHT,
    target_entity_id: str = "ci_seed",
    operator_id: str | None = "op_anna",
    status: CorrectionStatus = CorrectionStatus.APPLIED,
) -> Correction:
    async with session_maker() as session:
        row = Correction(
            target_entity_type=target_entity_type,
            target_entity_id=target_entity_id,
            correction_type=correction_type,
            operator_id=operator_id,
            status=status,
            payload={},
            original_snapshot={},
        )
        session.add(row)
        await session.flush()
        # ``created_at`` defaults to ``datetime.utcnow``; for deterministic
        # bucketing we override after the row exists.
        row.created_at = created_at
        await session.commit()
        await session.refresh(row)
        return row


def test_iso_week_start_snaps_to_monday_in_utc() -> None:
    # 2026-04-22 is a Wednesday — Monday of that ISO week is 2026-04-20.
    wednesday = datetime(2026, 4, 22, 14, 0, tzinfo=UTC)
    assert _iso_week_start(wednesday).isoformat() == "2026-04-20"
    # Naive datetimes are treated as UTC.
    naive_wednesday = datetime(2026, 4, 22, 14, 0)
    assert _iso_week_start(naive_wednesday).isoformat() == "2026-04-20"
    # Sunday lands on the *previous* Monday — ISO weeks start Monday.
    sunday = datetime(2026, 4, 26, 23, 0, tzinfo=UTC)
    assert _iso_week_start(sunday).isoformat() == "2026-04-20"


@pytest.mark.asyncio
async def test_get_metrics_seeds_empty_weeks_when_no_rows(session_maker) -> None:
    async with session_maker() as session:
        service = CorrectionService(session)
        result = await service.get_metrics(now=datetime(2026, 4, 22, 12, 0, tzinfo=UTC))

    # 12 weeks of lookback inclusive of the current week.
    assert len(result.weeks) == DEFAULT_METRICS_LOOKBACK_WEEKS
    assert result.weeks[-1].week_start.isoformat() == "2026-04-20"
    assert result.since.isoformat() == "2026-02-02"
    for week in result.weeks:
        assert week.by_entity_type == {}
        assert week.by_correction_type == {}
        assert week.operator_throughput == []
        assert week.rescore_outcomes.changed == 0
        assert week.rescore_outcomes.unchanged == 0
        assert week.rescore_outcomes.failed == 0


@pytest.mark.asyncio
async def test_get_metrics_buckets_by_entity_and_correction_type(session_maker) -> None:
    week_a = datetime(2026, 4, 14, 10, 0, tzinfo=UTC)  # Tue, week of 2026-04-13
    week_b = datetime(2026, 4, 21, 10, 0, tzinfo=UTC)  # Tue, week of 2026-04-20
    await _insert(session_maker, created_at=week_a, correction_type=CorrectionType.FIELD_EDIT)
    await _insert(session_maker, created_at=week_a, correction_type=CorrectionType.FIELD_EDIT)
    await _insert(session_maker, created_at=week_a, correction_type=CorrectionType.ANNOTATION)
    await _insert(session_maker, created_at=week_b, correction_type=CorrectionType.REJECT)

    async with session_maker() as session:
        service = CorrectionService(session)
        result = await service.get_metrics(now=datetime(2026, 4, 22, 12, 0, tzinfo=UTC))

    by_week = {w.week_start.isoformat(): w for w in result.weeks}
    assert by_week["2026-04-13"].by_correction_type == {"field_edit": 2, "annotation": 1}
    assert by_week["2026-04-13"].by_entity_type == {"commentary_insight": 3}
    assert by_week["2026-04-20"].by_correction_type == {"reject": 1}


@pytest.mark.asyncio
async def test_operator_throughput_counts_only_applied_operator_corrections(session_maker) -> None:
    week = datetime(2026, 4, 14, 10, 0, tzinfo=UTC)
    # Anna has two applied edits.
    await _insert(
        session_maker,
        created_at=week,
        operator_id="op_anna",
        status=CorrectionStatus.APPLIED,
    )
    await _insert(
        session_maker,
        created_at=week,
        operator_id="op_anna",
        status=CorrectionStatus.APPLIED,
    )
    # Ben has a pending edit — does not count toward throughput.
    await _insert(
        session_maker,
        created_at=week,
        operator_id="op_ben",
        status=CorrectionStatus.PENDING,
    )
    # Platform-emitted rescore requests carry no operator and should not
    # appear in the throughput list even when applied.
    await _insert(
        session_maker,
        created_at=week,
        operator_id=None,
        correction_type=CorrectionType.RESCORE_REQUEST,
        status=CorrectionStatus.APPLIED,
    )
    # Ben also has one applied edit so we can verify ordering by count desc.
    await _insert(
        session_maker,
        created_at=week,
        operator_id="op_ben",
        status=CorrectionStatus.APPLIED,
    )

    async with session_maker() as session:
        service = CorrectionService(session)
        result = await service.get_metrics(now=datetime(2026, 4, 22, 12, 0, tzinfo=UTC))

    bucket = next(w for w in result.weeks if w.week_start.isoformat() == "2026-04-13")
    assert [(t.operator_id, t.applied) for t in bucket.operator_throughput] == [
        ("op_anna", 2),
        ("op_ben", 1),
    ]


@pytest.mark.asyncio
async def test_rescore_outcomes_count_only_terminal_states(session_maker) -> None:
    week = datetime(2026, 4, 14, 10, 0, tzinfo=UTC)
    # CHANGED + UNCHANGED + FAILED count.
    for status in (
        CorrectionStatus.CHANGED,
        CorrectionStatus.UNCHANGED,
        CorrectionStatus.FAILED,
    ):
        await _insert(
            session_maker,
            created_at=week,
            correction_type=CorrectionType.RESCORE_REQUEST,
            operator_id=None,
            status=status,
        )
    # TRIGGERED rescore is in flight — must NOT count toward outcomes.
    await _insert(
        session_maker,
        created_at=week,
        correction_type=CorrectionType.RESCORE_REQUEST,
        operator_id=None,
        status=CorrectionStatus.TRIGGERED,
    )

    async with session_maker() as session:
        service = CorrectionService(session)
        result = await service.get_metrics(now=datetime(2026, 4, 22, 12, 0, tzinfo=UTC))

    bucket = next(w for w in result.weeks if w.week_start.isoformat() == "2026-04-13")
    assert bucket.rescore_outcomes.changed == 1
    assert bucket.rescore_outcomes.unchanged == 1
    assert bucket.rescore_outcomes.failed == 1


@pytest.mark.asyncio
async def test_get_metrics_excludes_rows_before_since(session_maker) -> None:
    old = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
    recent = datetime(2026, 4, 14, 10, 0, tzinfo=UTC)
    await _insert(session_maker, created_at=old)
    await _insert(session_maker, created_at=recent)

    async with session_maker() as session:
        service = CorrectionService(session)
        result = await service.get_metrics(
            since=recent.date() - timedelta(days=7),
            now=datetime(2026, 4, 22, 12, 0, tzinfo=UTC),
        )

    # ``since`` is snapped to its Monday (2026-04-06).
    assert result.since.isoformat() == "2026-04-06"
    totals = sum(sum(w.by_correction_type.values()) for w in result.weeks)
    assert totals == 1  # only the ``recent`` row falls inside the window


@pytest.mark.asyncio
async def test_get_metrics_emits_buckets_in_chronological_order(session_maker) -> None:
    async with session_maker() as session:
        service = CorrectionService(session)
        result = await service.get_metrics(now=datetime(2026, 4, 22, 12, 0, tzinfo=UTC))

    starts = [w.week_start for w in result.weeks]
    assert starts == sorted(starts)
