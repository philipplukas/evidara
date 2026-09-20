"""Processing reclaim entry point — the one place the sweep is wired up (#1038).

A document whose processing never terminated is invisible: `processing` means
*in flight* and it means *the worker died holding this*, and the ledger cannot
tell them apart. Measured 2026-09-19, 116 documents had been in that state for up
to 8d22h across two runs that both report `completed`, and `1901 known − 116 =
1785` is the search index's count exactly.

The schedule lives in Kubernetes
(``infra/hetzner/apps/processing-reclaim-cronjob.yaml``), which invokes the
``platform-control-processing-reclaim`` console script registered in
``pyproject.toml``. It is modelled on the retention sweep deliberately: a cron with
no human gate, nothing to resume and no need for durable execution. See
docs/runbooks/processing-reclaim.md.

:func:`run_processing_reclaim` is the single shared implementation. Two call sites
reuse it and neither re-implements the wiring:

- this module's :func:`main` (the CronJob, and the operator backfill),
- ``pc processing reclaim`` (the manual/interactive path).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_control.services.processing_reclaim_service import (
    ProcessingReclaimReport,
    ProcessingReclaimService,
)
from platform_control.services.processing_reconciliation import DEFAULT_PROCESSING_DEADLINE

LOGGER = logging.getLogger("platform_control.processing_reclaim")


async def run_processing_reclaim(
    *,
    dry_run: bool = False,
    deadline: timedelta = DEFAULT_PROCESSING_DEADLINE,
    run_id: str | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> ProcessingReclaimReport:
    """Execute one reclaim pass and return the report.

    ``session_factory`` defaults to the process-wide one; it is injectable so tests
    can pass a fixture's.
    """
    # Imported lazily so importing this module (e.g. for the console-script entry
    # point) does not pull in the FastAPI/asyncpg engine machinery at module load.
    from platform_control.database import get_session_maker

    maker = session_factory if session_factory is not None else get_session_maker()

    async with maker() as session:
        service = ProcessingReclaimService(session, deadline=deadline)
        return await service.reclaim(dry_run=dry_run, run_id=run_id)


def format_report(report: ProcessingReclaimReport) -> str:
    """Render the one-line summary operators (and `kubectl logs`) read."""
    prefix = "[dry-run] " if report.dry_run else ""
    return (
        f"{prefix}processing reclaim: "
        f"deadline_hours={report.deadline_hours:.0f} "
        f"units_examined={report.units_examined} "
        f"units_past_deadline={report.units_past_deadline} "
        f"units_reclaimed={report.units_reclaimed} "
        f"duplicates={report.duplicates} "
        f"runs_touched={len(report.runs_touched)}"
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="platform-control-processing-reclaim",
        description=(
            "Write a terminal processing status for every document that entered "
            "processing and never came out. Run on a schedule by the "
            "platform-control-processing-reclaim CronJob."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be reclaimed without writing anything.",
    )
    parser.add_argument(
        "--deadline-hours",
        type=float,
        default=DEFAULT_PROCESSING_DEADLINE.total_seconds() / 3600,
        help=(
            "How long to wait for a terminal status before reclaiming a unit "
            "(default: %(default)s). Lowering it does not make a unit broken; it "
            "only decides when the control plane stops waiting."
        ),
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Reclaim only this run's units. Omit to sweep every run.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Console-script entry point. Non-zero exit on failure so the CronJob fails loudly."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = parse_args(argv)
    if args.deadline_hours <= 0:
        # A zero or negative deadline reclaims work that is legitimately in flight.
        # Refused here rather than clamped: a mistyped flag should fail, not quietly
        # become a different command.
        print("--deadline-hours must be positive", file=sys.stderr)
        return 2

    report = asyncio.run(
        run_processing_reclaim(
            dry_run=args.dry_run,
            deadline=timedelta(hours=args.deadline_hours),
            run_id=args.run_id,
        )
    )

    summary = format_report(report)
    LOGGER.info(
        summary,
        extra={
            "extra_fields": {
                "event": "processing_reclaim_completed",
                "dry_run": report.dry_run,
                "deadline_hours": report.deadline_hours,
                "units_examined": report.units_examined,
                "units_past_deadline": report.units_past_deadline,
                "units_reclaimed": report.units_reclaimed,
                "duplicates": report.duplicates,
                "runs_touched": report.runs_touched,
            }
        },
    )
    print(summary)
    return 0


if __name__ == "__main__":  # pragma: no cover - script entry
    sys.exit(main())
