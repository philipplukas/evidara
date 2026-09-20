"""Give a stranded processing unit a terminal status, from outside the worker (#1038).

THE POINT IS WHERE THIS RUNS, NOT WHAT IT WRITES
------------------------------------------------
A `finally:` in document-intelligence cannot close this hole, because the consumer
is what dies. Neither can a callback, a shutdown hook or a best-effort `except`:
each of them runs inside the process whose death is the failure. The only writer
that survives it is one that never took part — the control plane, on a clock, with
no memory of the work it is terminating.

So this sweep asks one question that needs no cooperation from anybody:

    which processing units announced themselves and then went quiet for longer
    than we are willing to wait?

and answers it by writing the terminal row nobody else wrote.

WHAT THE ROW CLAIMS, AND WHAT IT REFUSES TO CLAIM
-------------------------------------------------
`FAILED` with `error_code=processing_deadline_exceeded`. Read it as *the control
plane stopped waiting*, never as *document-intelligence reported a failure* — DI
did not report anything, which is the whole problem. The summary says so in words,
because a terminal status that silently invents a cause is the same defect wearing
the opposite mask.

The cause genuinely is not known from here, and measured on 2026-09-19 at least
three are live candidates for the 116 stranded rows:

* the worker died mid-document (`#1012`'s OOM);
* the status event was published and lost;
* DI made a terminal decision it never publishes. ADR-0047's quarantine path
  emits `accepted` and `processing` and then deliberately stops
  (`document-intelligence/src/document_intelligence/pipeline.py:487`), so a
  quarantined document leaves *exactly* this fingerprint. `quarantined`,
  `failed`, `withdrawn` and `skipped_duplicate` are declared in
  `ProcessingStatus`, modelled in the event contract, counted by
  `CoverageService._quarantined_by_jurisdiction` — and emitted by nothing:
  `build_processing_status_event` has three call sites and they pass `accepted`,
  `processing` and `canonical_ready`. That is a follow-up on DI's surface, not
  this one, and it does not change what this sweep must do, because the sweep
  exists for the causes nobody will ever get an event out for.

IDEMPOTENCE
-----------
`event_id` is derived from the unit id, so a second pass over the same unit
collides on the primary key and is recorded as a duplicate rather than a second
terminal row. Belt and braces: once the row exists the unit holds a terminal
status and the query below no longer selects it at all.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.domain import TERMINAL_PROCESSING_STATUSES, ProcessingStatus
from platform_control.models.processing_status_update import ProcessingStatusUpdate
from platform_control.observability import metrics
from platform_control.services.processing_reconciliation import (
    DEFAULT_PROCESSING_DEADLINE,
    as_utc,
)

#: The error code every reclaimed row carries. It is owned by this module and by
#: nothing else: document-intelligence emits no `failed` status at all today, so a
#: row bearing this slug was written here, by a clock, and never by a worker
#: reporting on its own work. `test_reclaim_error_code_is_not_a_document_intelligence_code`
#: pins that.
PROCESSING_DEADLINE_EXCEEDED = "processing_deadline_exceeded"

#: Crockford base32, lowercase — the alphabet `^evt_[0-9a-hjkmnp-tv-z]{26}$` in
#: `contracts/events/document-processing-status-updated.schema.json` accepts. A
#: reclaimed row is not an event and is never published, but it lands in the same
#: table as rows that are, and a reader should not have to special-case its shape.
_CROCKFORD32 = "0123456789abcdefghjkmnpqrstvwxyz"


def reclaim_event_id(processing_manifest_id: str) -> str:
    """A stable `evt_` id for the terminal row of one processing unit.

    Deterministic on purpose: two sweeps racing each other (a manual backfill
    against the CronJob, say) must not be able to write two terminal rows for one
    unit. The second insert hits the primary key and is reported as a duplicate.
    """
    digest = hashlib.sha256(f"reclaim:{processing_manifest_id}".encode()).digest()
    value = int.from_bytes(digest, "big")
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD32[value & 31])
        value >>= 5
    return "evt_" + "".join(reversed(chars))


@dataclass
class ProcessingReclaimReport:
    """What one sweep found and what it did about it.

    `units_examined` and `units_past_deadline` are reported even when nothing is
    written, including in `--dry-run`, so "the sweep ran and found nothing" and
    "the sweep ran and declined to act" are different lines in the log rather than
    the same silence.
    """

    units_examined: int = 0
    units_past_deadline: int = 0
    units_reclaimed: int = 0
    duplicates: int = 0
    deadline_hours: float = 0.0
    dry_run: bool = False
    runs_touched: list[str] = field(default_factory=list)


class ProcessingReclaimService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        deadline: timedelta = DEFAULT_PROCESSING_DEADLINE,
    ) -> None:
        self.session = session
        self.deadline = deadline

    async def reclaim(
        self,
        *,
        now: datetime | None = None,
        run_id: str | None = None,
        dry_run: bool = False,
    ) -> ProcessingReclaimReport:
        moment = now or datetime.now(UTC)
        cutoff = moment - self.deadline
        report = ProcessingReclaimReport(
            deadline_hours=self.deadline.total_seconds() / 3600,
            dry_run=dry_run,
        )

        for unit in await self._non_terminal_units(run_id=run_id):
            report.units_examined += 1
            if unit.last_seen_at > cutoff:
                continue
            report.units_past_deadline += 1
            if unit.run_id not in report.runs_touched:
                report.runs_touched.append(unit.run_id)
            if dry_run:
                continue
            if await self._write_terminal_row(unit, now=moment):
                report.units_reclaimed += 1
            else:
                report.duplicates += 1

        metrics.record_processing_units_reclaimed(report.units_reclaimed)
        return report

    async def _non_terminal_units(self, *, run_id: str | None) -> list[_StrandedUnit]:
        """Every processing unit holding no terminal status, newest row per unit.

        The `NOT IN` subquery narrows the fetch to units that could possibly be
        stranded, which is what keeps this from loading a table that grows one row
        per document forever. It is deliberately **not** narrowed by time: a
        `WHERE occurred_at >= now() - 90d` would make "never stranded" and
        "stranded before the window" indistinguishable, and the oldest row this was
        written for is already 8d22h old and counting.
        """
        terminal_units = select(ProcessingStatusUpdate.processing_manifest_id).where(
            ProcessingStatusUpdate.status.in_(TERMINAL_PROCESSING_STATUSES)
        )
        statement = select(ProcessingStatusUpdate).where(
            ProcessingStatusUpdate.processing_manifest_id.not_in(terminal_units)
        )
        if run_id is not None:
            statement = statement.where(ProcessingStatusUpdate.run_id == run_id)

        grouped: dict[str, list[ProcessingStatusUpdate]] = {}
        for row in await self.session.scalars(statement):
            grouped.setdefault(row.processing_manifest_id, []).append(row)

        units = [self._unit_from_rows(unit_id, rows) for unit_id, rows in grouped.items()]
        return sorted(units, key=lambda unit: unit.last_seen_at)

    @staticmethod
    def _unit_from_rows(unit_id: str, rows: list[ProcessingStatusUpdate]) -> _StrandedUnit:
        """Collapse one unit's rows into the facts the terminal row needs.

        The newest row supplies the timestamp and the last status. Every other
        field takes the first non-null value seen across the unit's rows: DI's
        `accepted` and `processing` carry the same provenance, but a nullable
        column that happens to be absent on the newest row must not erase what an
        earlier one recorded.
        """
        ordered = sorted(rows, key=lambda row: as_utc(row.occurred_at))
        newest = ordered[-1]

        def first(attribute: str) -> object | None:
            for row in ordered:
                value = getattr(row, attribute)
                if value is not None:
                    return value
            return None

        return _StrandedUnit(
            processing_manifest_id=unit_id,
            run_id=newest.run_id,
            processing_version=newest.processing_version,
            source_snapshot_id=first("source_snapshot_id"),  # type: ignore[arg-type]
            bundle_manifest_id=first("bundle_manifest_id"),  # type: ignore[arg-type]
            document_id=first("document_id"),  # type: ignore[arg-type]
            document_revision=first("document_revision"),  # type: ignore[arg-type]
            last_status=newest.status,
            last_seen_at=as_utc(newest.occurred_at),
        )

    async def _write_terminal_row(self, unit: _StrandedUnit, *, now: datetime) -> bool:
        """Insert the terminal row. False means it was already there."""
        silent_for = now - unit.last_seen_at
        row = ProcessingStatusUpdate(
            event_id=reclaim_event_id(unit.processing_manifest_id),
            run_id=unit.run_id,
            processing_manifest_id=unit.processing_manifest_id,
            processing_version=unit.processing_version,
            status=ProcessingStatus.FAILED,
            occurred_at=now,
            source_snapshot_id=unit.source_snapshot_id,
            bundle_manifest_id=unit.bundle_manifest_id,
            document_id=unit.document_id,
            document_revision=unit.document_revision,
            error_code=PROCESSING_DEADLINE_EXCEEDED,
            error_summary=(
                f"No terminal processing status arrived within "
                f"{self.deadline.total_seconds() / 3600:.0f}h. The last status was "
                f"`{unit.last_status.value}` at {unit.last_seen_at.isoformat()}, "
                f"{silent_for.days}d{silent_for.seconds // 3600}h ago. Written by the "
                "platform-control reclaim sweep, not reported by document-intelligence: "
                "the cause is unknown from here and may be a dead worker, a lost event, "
                "or a terminal decision DI never published."
            ),
        )
        self.session.add(row)
        try:
            await self.session.commit()
            return True
        except IntegrityError:
            await self.session.rollback()
            return False


@dataclass(frozen=True, slots=True)
class _StrandedUnit:
    processing_manifest_id: str
    run_id: str
    processing_version: str
    source_snapshot_id: str | None
    bundle_manifest_id: str | None
    document_id: str | None
    document_revision: int | None
    last_status: ProcessingStatus
    last_seen_at: datetime
