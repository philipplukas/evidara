"""``pc processing reclaim`` — the manual path into the processing reclaim sweep.

The sweep itself lives in :mod:`platform_control.processing_reclaim` and is shared
with the ``platform-control-processing-reclaim`` console script that the Kubernetes
CronJob runs (#1038). This subcommand is the interactive alias operators reach for
— including for the one-off backfill of the 116 documents that were already
stranded when the sweep shipped; it must not re-implement the sweep.
"""

from __future__ import annotations

import argparse
from datetime import timedelta


async def run_from_args(namespace: argparse.Namespace) -> int:
    from platform_control.processing_reclaim import format_report, run_processing_reclaim

    if namespace.deadline_hours <= 0:
        print("--deadline-hours must be positive")
        return 2

    report = await run_processing_reclaim(
        dry_run=namespace.dry_run,
        deadline=timedelta(hours=namespace.deadline_hours),
        run_id=namespace.run_id,
    )
    print(format_report(report))
    for run_id in report.runs_touched:
        print(f"  run {run_id}")
    return 0


__all__ = ["run_from_args"]
