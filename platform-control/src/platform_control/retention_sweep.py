"""Retention sweep entry point — the one place the sweep is wired up.

Hard-delete retention (:class:`CompliancePolicy.retention_days`) is a legal
obligation in some jurisdictions, so the sweep must run on a schedule that is
independent of any optional subsystem. It is a cron: it has no human gate, no
multi-hour fan-out, and nothing to resume. It does not need durable execution.

The schedule lives in Kubernetes (``infra/hetzner/apps/retention-sweep-cronjob.yaml``),
which invokes the ``platform-control-retention-sweep`` console script registered
in ``pyproject.toml``. See ADR-0031 and docs/runbooks/retention-sweep.md.

:func:`run_retention_sweep` is the single shared implementation. Three call
sites reuse it and none of them re-implement the wiring:

- this module's :func:`main` (the CronJob),
- ``pc retention sweep`` (the manual/interactive path),
- ``RetentionActivities.run_retention_sweep`` (kept so the Temporal code stays
  correct if a worker is ever deployed — ADR-0031 keeps Temporal, just off).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_control.services.retention_service import RetentionService, RetentionSweepReport

LOGGER = logging.getLogger("platform_control.retention_sweep")


async def run_retention_sweep(
    *,
    dry_run: bool = False,
    settings: object | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> RetentionSweepReport:
    """Execute one retention sweep pass and return the report.

    ``settings`` and ``session_factory`` default to the process-wide ones; they
    are injectable so the Temporal activity can pass the worker's factory and
    tests can pass a fixture's.
    """
    # Imported lazily so importing this module (e.g. for the console-script entry
    # point) does not pull in the FastAPI/asyncpg engine machinery at module load.
    from platform_control.config import get_settings
    from platform_control.database import get_session_maker
    from platform_control.integrations import get_artifact_store

    active_settings = settings if settings is not None else get_settings()
    maker = session_factory if session_factory is not None else get_session_maker()
    artifact_store = get_artifact_store(active_settings)  # type: ignore[arg-type]

    async with maker() as session:
        service = RetentionService(session=session, artifact_store=artifact_store)
        return await service.sweep(dry_run=dry_run)


def format_report(report: RetentionSweepReport, *, dry_run: bool) -> str:
    """Render the one-line summary operators (and `kubectl logs`) read."""
    prefix = "[dry-run] " if dry_run else ""
    return (
        f"{prefix}retention sweep: "
        f"policies_applied={report.policies_applied} "
        f"artifacts_purged={report.artifacts_purged} "
        f"resources_purged={report.resources_purged} "
        f"blobs_deleted={report.blobs_deleted}"
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="platform-control-retention-sweep",
        description=(
            "Purge raw artifacts past their jurisdiction's CompliancePolicy.retention_days. "
            "Run on a schedule by the platform-control-retention-sweep CronJob."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be purged without deleting anything.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Console-script entry point. Non-zero exit on failure so the CronJob fails loudly."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = parse_args(argv)

    report = asyncio.run(run_retention_sweep(dry_run=args.dry_run))

    summary = format_report(report, dry_run=args.dry_run)
    LOGGER.info(
        summary,
        extra={
            "extra_fields": {
                "event": "retention_sweep_completed",
                "dry_run": args.dry_run,
                "policies_applied": report.policies_applied,
                "artifacts_purged": report.artifacts_purged,
                "resources_purged": report.resources_purged,
                "blobs_deleted": report.blobs_deleted,
            }
        },
    )
    print(summary)
    return 0


if __name__ == "__main__":  # pragma: no cover - script entry
    sys.exit(main())
