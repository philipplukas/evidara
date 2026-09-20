"""Count a run's started processing units against the ones that finished (#1038).

WHY THIS EXISTS, WHEN A RECONCILER ALREADY DID
----------------------------------------------
`coverage_reconciliation` reconciles **acquisition**: what discovery found against
what the source says it publishes. Measured 2026-09-19, it held 7 rows, every one
`expected 1378 / observed 1378`, and it reported both
`run_01m26a84j0gdmeh9g5f8b1k36k` and `run_01m2q5fsqmarc3mxvfpsw1jjdt` as fully
reconciled while each of them held 58 documents that entered processing and never
came out. Both runs report `status=completed`. `1901 known − 116 stuck = 1785`,
which is the search index's document count exactly — the documents are absent from
search and nothing said so for nine days.

So this is not a second copy of that reconciler, it is the half of the pipeline it
does not look at. It is deliberately session-free and side-effect-free, for the
same reason its acquisition sibling is: the counting rule is the part most likely
to be wrong, and it should be testable without a database or a dispatched run.

WHAT IS COUNTED, AND WHY NOT `document_id`
------------------------------------------
Units are keyed on **`processing_manifest_id`**, which is `NOT NULL` and is minted
once per document attempt (`document-intelligence/.../pipeline.py` mints a `pm_`
id before it emits `accepted`). `document_id` is nullable, so keying on it would
collapse every row that carries none into a single bucket and undercount — the
same trap `CoverageService._quarantined_by_jurisdiction` writes down for its own
counts. A document processed twice is two attempts and two manifests, and each one
owes a terminal status.

TWO NUMBERS, NOT ONE
--------------------
`unterminated_units` is the whole truth and has no time window: every unit that
started and has not finished, however recently. `unterminated_units_past_deadline`
is the actionable subset — the ones that have been silent longer than the control
plane is willing to wait.

Reporting only the second would make the guard a tuned floor, and a floor tuned to
one sample withholds the next one. Reporting only the first would fire on every
healthy run that is still mid-flight. The verdict is driven by the **total**, so it
cannot be quieted by choosing a deadline; the deadline decides only how loudly a
surface renders it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from platform_control.domain import (
    TERMINAL_PROCESSING_STATUSES,
    ProcessingReconciliationVerdict,
    ProcessingStatus,
)

#: How long the control plane waits for a terminal status before it calls a unit
#: stranded. Not a judgement about the document — it is when *we* stop waiting.
#:
#: 24h, against measured batches: the 2026-09-17 run's processing statuses span
#: 07:56Z..13:48Z (under 6 hours end to end) and the oldest stranded row is 8d22h
#: old. A deadline inside that gap separates the two populations with an order of
#: magnitude to spare in both directions, which is the only calibration claim made
#: here. `unterminated_units` is reported regardless of it.
DEFAULT_PROCESSING_DEADLINE = timedelta(hours=24)

#: Cap on the per-unit sample carried alongside the counts. The counts are computed
#: over every unit; only the listing is bounded, so truncating the sample can never
#: change the verdict.
MAX_UNTERMINATED_SAMPLE = 20


class StatusRow(Protocol):
    """The shape `reconcile_processing` needs — satisfied by `ProcessingStatusUpdate`.

    A Protocol rather than the ORM model so the rule can be exercised on plain
    objects, and so this module imports no SQLAlchemy.
    """

    processing_manifest_id: str
    document_id: str | None
    status: ProcessingStatus
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class UnterminatedUnit:
    """One processing unit that started and never reached a terminal status."""

    processing_manifest_id: str
    document_id: str | None
    last_status: ProcessingStatus
    last_seen_at: datetime
    #: True when `last_seen_at` is older than the deadline. Carried per unit so an
    #: operator reading the sample can tell which rows the reclaimer would act on.
    past_deadline: bool


@dataclass(frozen=True, slots=True)
class ProcessingReconciliation:
    """A run's processing ledger, reconciled.

    `observed_units` is the denominator this can actually stand behind: units the
    control plane was *told about*. It is not the number of documents the run
    handed to document-intelligence — nothing persists that per run today — so a
    worker that died before emitting its first `accepted` is invisible here and
    shows up as `NOTHING_OBSERVED` only if it took the whole run down with it. That
    gap is named rather than papered over; `unterminated_units` covers every unit
    that did announce itself, which is the case this was built for.
    """

    observed_units: int
    terminal_units: int
    unterminated_units: int
    unterminated_units_past_deadline: int
    oldest_unterminated_at: datetime | None
    verdict: ProcessingReconciliationVerdict
    unterminated: tuple[UnterminatedUnit, ...]

    @property
    def is_clean(self) -> bool:
        """True only for `RECONCILED`.

        `NOTHING_OBSERVED` is explicitly not clean. A caller writing
        `verdict != UNTERMINATED` would let it through, which is the silent-zero
        reading this whole module exists to refuse.
        """
        return self.verdict is ProcessingReconciliationVerdict.RECONCILED


def as_utc(value: datetime) -> datetime:
    """Attach UTC to a naive timestamp rather than comparing it to an aware `now`.

    `occurred_at` is `DateTime(timezone=True)`, which Postgres honours and SQLite
    does not — the test schema hands back naive datetimes and `aware - naive`
    raises `TypeError`. Assuming UTC is correct for both: every writer of this
    column writes UTC.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def reconcile_processing(
    rows: Iterable[StatusRow],
    *,
    now: datetime | None = None,
    deadline: timedelta = DEFAULT_PROCESSING_DEADLINE,
) -> ProcessingReconciliation:
    """Reconcile one run's processing status rows.

    `rows` may arrive in any order and may contain several rows per unit; only the
    set of statuses per unit and the latest `occurred_at` matter.
    """
    moment = now or datetime.now(UTC)
    cutoff = moment - deadline

    statuses: dict[str, set[ProcessingStatus]] = {}
    last_seen: dict[str, datetime] = {}
    last_status: dict[str, ProcessingStatus] = {}
    document_ids: dict[str, str | None] = {}

    for row in rows:
        unit = row.processing_manifest_id
        occurred_at = as_utc(row.occurred_at)
        statuses.setdefault(unit, set()).add(row.status)
        if unit not in last_seen or occurred_at >= last_seen[unit]:
            last_seen[unit] = occurred_at
            last_status[unit] = row.status
        # First non-null wins: a later row that carries none must not erase the
        # identifier an earlier one supplied.
        if document_ids.get(unit) is None:
            document_ids[unit] = row.document_id

    unterminated: list[UnterminatedUnit] = []
    terminal_units = 0
    for unit, seen in statuses.items():
        if seen & TERMINAL_PROCESSING_STATUSES:
            terminal_units += 1
            continue
        unterminated.append(
            UnterminatedUnit(
                processing_manifest_id=unit,
                document_id=document_ids.get(unit),
                last_status=last_status[unit],
                last_seen_at=last_seen[unit],
                past_deadline=last_seen[unit] <= cutoff,
            )
        )

    observed_units = len(statuses)
    # Oldest first, so a truncated sample shows the worst rather than an arbitrary
    # slice of it.
    unterminated.sort(key=lambda unit: unit.last_seen_at)

    if observed_units == 0:
        verdict = ProcessingReconciliationVerdict.NOTHING_OBSERVED
    elif unterminated:
        verdict = ProcessingReconciliationVerdict.UNTERMINATED
    else:
        verdict = ProcessingReconciliationVerdict.RECONCILED

    return ProcessingReconciliation(
        observed_units=observed_units,
        terminal_units=terminal_units,
        unterminated_units=len(unterminated),
        unterminated_units_past_deadline=sum(1 for unit in unterminated if unit.past_deadline),
        oldest_unterminated_at=unterminated[0].last_seen_at if unterminated else None,
        verdict=verdict,
        unterminated=tuple(unterminated[:MAX_UNTERMINATED_SAMPLE]),
    )
