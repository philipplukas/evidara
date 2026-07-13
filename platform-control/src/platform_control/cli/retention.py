"""``pc retention sweep`` — the manual path into the retention sweep.

The sweep itself lives in :mod:`platform_control.retention_sweep` and is shared
with the ``platform-control-retention-sweep`` console script that the Kubernetes
CronJob runs (ADR-0031). This subcommand is the interactive alias operators reach
for; it must not re-implement the sweep.
"""

from __future__ import annotations

import argparse


async def run_from_args(namespace: argparse.Namespace) -> int:
    from platform_control.retention_sweep import format_report, run_retention_sweep

    report = await run_retention_sweep(dry_run=namespace.dry_run)
    print(format_report(report, dry_run=namespace.dry_run))
    return 0


__all__ = ["run_from_args"]
