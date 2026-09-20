"""The processing reconciliation rule, exercised without a database (#1038).

Every fixture here is shaped after what production actually held on 2026-09-19:
116 documents stranded in `processing` across two runs that both report
`completed`, the oldest 8d22h old, `1901 known − 116 = 1785` matching the search
index exactly.

The tests are named so that deleting a guard names its own victim. Each guard's
mutation is recorded in the docstring that asserts it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from platform_control.domain import (
    NON_TERMINAL_PROCESSING_STATUSES,
    TERMINAL_PROCESSING_STATUSES,
    ProcessingReconciliationVerdict,
    ProcessingStatus,
)
from platform_control.services.processing_reconciliation import (
    DEFAULT_PROCESSING_DEADLINE,
    MAX_UNTERMINATED_SAMPLE,
    reconcile_processing,
)

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
#: The 2026-09-10 run's first status row, from the issue's measurement.
STRANDED_AT = datetime(2026, 9, 10, 18, 49, 37, tzinfo=UTC)


@dataclass
class Row:
    """A `ProcessingStatusUpdate` reduced to the four fields the rule reads."""

    processing_manifest_id: str
    status: ProcessingStatus
    occurred_at: datetime
    document_id: str | None = None


def _stranded_unit(index: int, *, at: datetime = STRANDED_AT) -> list[Row]:
    """The production fingerprint: `accepted` then `processing`, then nothing.

    That pair is what document-intelligence writes before it starts work, and it
    is all that survives when the work never finishes.
    """
    return [
        Row(f"pm_stranded_{index}", ProcessingStatus.ACCEPTED, at, f"doc_{index}"),
        Row(f"pm_stranded_{index}", ProcessingStatus.PROCESSING, at, f"doc_{index}"),
    ]


def _finished_unit(index: int, *, at: datetime) -> list[Row]:
    """`accepted` -> `processing` -> `canonical_ready`, in that chronological order.

    The timestamps are staggered rather than shared so `canonical_ready` really is
    this unit's newest row — which is what makes it capable of masking a stranded
    unit in the same run.
    """
    return [
        Row(f"pm_done_{index}", ProcessingStatus.ACCEPTED, at, f"doc_done_{index}"),
        Row(
            f"pm_done_{index}",
            ProcessingStatus.PROCESSING,
            at + timedelta(seconds=1),
            f"doc_done_{index}",
        ),
        Row(
            f"pm_done_{index}",
            ProcessingStatus.CANONICAL_READY,
            at + timedelta(seconds=2),
            f"doc_done_{index}",
        ),
    ]


def test_every_processing_status_is_classified() -> None:
    """A new status must land in exactly one of the two sets.

    Without this, adding a status and forgetting the terminal set makes it
    non-terminal by default — every document carrying it would be reported
    stranded forever, and nothing else in the suite would notice.
    """
    assert TERMINAL_PROCESSING_STATUSES | NON_TERMINAL_PROCESSING_STATUSES == set(ProcessingStatus)
    assert not (TERMINAL_PROCESSING_STATUSES & NON_TERMINAL_PROCESSING_STATUSES)
    assert NON_TERMINAL_PROCESSING_STATUSES == {
        ProcessingStatus.ACCEPTED,
        ProcessingStatus.PROCESSING,
    }


def test_the_production_shape_reports_unterminated_not_reconciled() -> None:
    """58 stranded units beside 900 finished ones — the 2026-09-10 run.

    MUTATION: drop the `seen & TERMINAL_PROCESSING_STATUSES` branch in
    `reconcile_processing` (count every unit as terminal) and this fails on
    `verdict`.
    """
    rows: list[Row] = []
    for index in range(58):
        rows.extend(_stranded_unit(index))
    for index in range(900):
        rows.extend(_finished_unit(index, at=STRANDED_AT))

    result = reconcile_processing(rows, now=NOW)

    assert result.verdict is ProcessingReconciliationVerdict.UNTERMINATED
    assert result.observed_units == 958
    assert result.terminal_units == 900
    assert result.unterminated_units == 58
    assert result.unterminated_units_past_deadline == 58
    assert result.oldest_unterminated_at == STRANDED_AT
    assert result.is_clean is False


def test_a_newest_row_of_canonical_ready_cannot_hide_a_stranded_unit() -> None:
    """The exact mechanism that hid 116 documents for nine days.

    `get_pipeline_health` read the run's single newest status row. On a run where
    most documents succeeded, that row is a `canonical_ready` — so the stage
    reported `ok` over a run that had stopped reporting on 58 documents.

    MUTATION: reconcile only the newest row per run instead of every unit, and
    this fails.
    """
    rows = [
        *_stranded_unit(0),
        *_finished_unit(0, at=NOW - timedelta(minutes=1)),
    ]

    result = reconcile_processing(rows, now=NOW)

    newest = max(rows, key=lambda row: row.occurred_at)
    assert newest.status is ProcessingStatus.CANONICAL_READY
    assert result.verdict is ProcessingReconciliationVerdict.UNTERMINATED
    assert result.unterminated_units == 1


def test_no_rows_at_all_is_nothing_observed_and_is_not_clean() -> None:
    """Zero over zero is unknown, never a pass.

    A run that published bundle events and produced no status row is a worker that
    died before it said anything. Reporting that as `RECONCILED` would be the
    silent-zero reading this module exists to refuse.

    MUTATION: make `NOTHING_OBSERVED` satisfy `is_clean` and this fails.
    """
    result = reconcile_processing([], now=NOW)

    assert result.verdict is ProcessingReconciliationVerdict.NOTHING_OBSERVED
    assert result.is_clean is False
    assert result.observed_units == 0
    assert result.unterminated_units == 0


def test_a_fully_finished_run_reconciles() -> None:
    """The guard must be able to say yes, or it is not a guard."""
    rows: list[Row] = []
    for index in range(12):
        rows.extend(_finished_unit(index, at=STRANDED_AT))

    result = reconcile_processing(rows, now=NOW)

    assert result.verdict is ProcessingReconciliationVerdict.RECONCILED
    assert result.is_clean is True
    assert result.terminal_units == 12
    assert result.unterminated == ()


def test_units_are_keyed_on_the_manifest_id_not_the_document_id() -> None:
    """`document_id` is nullable; keying on it collapses every null into one unit.

    ADR-0047 quarantine rows and any pre-identity failure carry no `document_id`,
    so this is not hypothetical.

    MUTATION: key the dicts in `reconcile_processing` on `row.document_id` and
    this reports 1 unterminated unit instead of 3.
    """
    rows = [
        Row("pm_a", ProcessingStatus.PROCESSING, STRANDED_AT, None),
        Row("pm_b", ProcessingStatus.PROCESSING, STRANDED_AT, None),
        Row("pm_c", ProcessingStatus.PROCESSING, STRANDED_AT, None),
    ]

    result = reconcile_processing(rows, now=NOW)

    assert result.observed_units == 3
    assert result.unterminated_units == 3


def test_quarantined_is_terminal_and_is_not_reported_stranded() -> None:
    """A quarantined document is finished, not stuck (ADR-0047).

    Calling it stranded sends an operator hunting a failure that did not happen,
    and the reclaim sweep would then write a second terminal row over a decision
    that was already made.
    """
    rows = [
        Row("pm_q", ProcessingStatus.ACCEPTED, STRANDED_AT),
        Row("pm_q", ProcessingStatus.PROCESSING, STRANDED_AT),
        Row("pm_q", ProcessingStatus.QUARANTINED, STRANDED_AT),
    ]

    result = reconcile_processing(rows, now=NOW)

    assert result.verdict is ProcessingReconciliationVerdict.RECONCILED
    assert result.terminal_units == 1


def test_work_inside_the_deadline_is_counted_but_not_past_it() -> None:
    """Two numbers, and only one of them has a time window.

    A run that finished acquisition a minute ago legitimately holds units that
    have not terminated. They are reported — `unterminated_units` has no window —
    but they are not actionable, and a surface that cried failure over them would
    be switched off within a week.

    MUTATION: make `unterminated_units` itself respect the deadline and this fails
    on the first assertion, which is the whole point: the total is not tunable.
    """
    rows = _stranded_unit(0, at=NOW - timedelta(minutes=5))

    result = reconcile_processing(rows, now=NOW, deadline=DEFAULT_PROCESSING_DEADLINE)

    assert result.unterminated_units == 1
    assert result.unterminated_units_past_deadline == 0
    assert result.verdict is ProcessingReconciliationVerdict.UNTERMINATED
    assert result.unterminated[0].past_deadline is False


def test_the_sample_is_bounded_but_the_counts_and_verdict_are_not() -> None:
    """Truncating the listing must not be able to quieten the verdict.

    MUTATION: compute `unterminated_units` from the truncated tuple rather than
    the full list and this reports 20 instead of 50.
    """
    rows: list[Row] = []
    for index in range(50):
        rows.extend(_stranded_unit(index))

    result = reconcile_processing(rows, now=NOW)

    assert result.unterminated_units == 50
    assert result.unterminated_units_past_deadline == 50
    assert len(result.unterminated) == MAX_UNTERMINATED_SAMPLE
    assert result.verdict is ProcessingReconciliationVerdict.UNTERMINATED


def test_the_sample_shows_the_oldest_units_first() -> None:
    """A truncated sample must show the worst, not an arbitrary slice of it."""
    rows = [
        *_stranded_unit(0, at=NOW - timedelta(days=1)),
        *_stranded_unit(1, at=STRANDED_AT),
        *_stranded_unit(2, at=NOW - timedelta(days=3)),
    ]

    result = reconcile_processing(rows, now=NOW)

    assert [unit.processing_manifest_id for unit in result.unterminated] == [
        "pm_stranded_1",
        "pm_stranded_2",
        "pm_stranded_0",
    ]


def test_a_naive_timestamp_is_read_as_utc_rather_than_raising() -> None:
    """SQLite hands back naive datetimes for `DateTime(timezone=True)`.

    Every writer of `occurred_at` writes UTC, so assuming UTC is correct — and
    `aware - naive` raises `TypeError`, which would take the whole read model down
    on the test schema and on any SQLite-backed environment.

    MUTATION: drop `as_utc` from `reconcile_processing` and this raises.
    """
    naive = STRANDED_AT.replace(tzinfo=None)
    rows = [Row("pm_naive", ProcessingStatus.PROCESSING, naive, "doc_naive")]

    result = reconcile_processing(rows, now=NOW)

    assert result.unterminated_units_past_deadline == 1
    assert result.oldest_unterminated_at == STRANDED_AT


def test_the_last_status_reported_is_the_newest_row_not_the_last_one_seen() -> None:
    """Rows arrive in whatever order the query returns them."""
    rows = [
        Row("pm_x", ProcessingStatus.PROCESSING, STRANDED_AT + timedelta(seconds=1)),
        Row("pm_x", ProcessingStatus.ACCEPTED, STRANDED_AT),
    ]

    result = reconcile_processing(rows, now=NOW)

    assert result.unterminated[0].last_status is ProcessingStatus.PROCESSING
    assert result.unterminated[0].last_seen_at == STRANDED_AT + timedelta(seconds=1)


def test_a_document_id_on_an_earlier_row_is_not_erased_by_a_later_null() -> None:
    """The identifier an operator needs must survive a row that carries none."""
    rows = [
        Row("pm_y", ProcessingStatus.ACCEPTED, STRANDED_AT, "doc_y"),
        Row("pm_y", ProcessingStatus.PROCESSING, STRANDED_AT + timedelta(seconds=1), None),
    ]

    result = reconcile_processing(rows, now=NOW)

    assert result.unterminated[0].document_id == "doc_y"
