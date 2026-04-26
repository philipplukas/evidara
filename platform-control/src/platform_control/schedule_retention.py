"""Idempotently create or update the retention-sweep Temporal schedule.

Registered as ``platform-control-schedule-retention`` in ``pyproject.toml``.
Operators run this once per environment (dev/staging/prod) after deploying
the worker with :class:`RetentionSweepWorkflow`. Re-running is a no-op when
the schedule already matches.

Cron default: ``0 4 * * *`` (daily at 04:00 UTC) — low-traffic window for
most of our jurisdictions. Override via ``--cron`` if a tenant's window
differs.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import timedelta

from temporalio.client import (
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleSpec,
    ScheduleState,
    ScheduleUpdate,
    ScheduleUpdateInput,
)

from platform_control.config import get_settings
from platform_control.temporal.client import connect_temporal

LOGGER = logging.getLogger("platform_control.schedule_retention")

_DEFAULT_SCHEDULE_ID = "retention-sweep"
_DEFAULT_CRON = "0 4 * * *"
_WORKFLOW_ID = "retention-sweep"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or update the retention-sweep Temporal schedule.",
    )
    parser.add_argument(
        "--schedule-id",
        default=_DEFAULT_SCHEDULE_ID,
        help="Schedule ID on the Temporal namespace. Defaults to 'retention-sweep'.",
    )
    parser.add_argument(
        "--cron",
        default=_DEFAULT_CRON,
        help="Cron expression. Defaults to '0 4 * * *' (daily at 04:00 UTC).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Schedule the workflow with dry_run=True on each invocation. Useful "
            "for validating the sweep touches the expected artifacts before "
            "enabling hard delete."
        ),
    )
    parser.add_argument(
        "--paused",
        action="store_true",
        help="Create the schedule paused. Unpause from the Temporal UI when ready.",
    )
    return parser.parse_args()


def build_schedule(
    *,
    task_queue: str,
    cron: str,
    dry_run: bool,
    paused: bool,
) -> Schedule:
    """Return the Schedule definition the CLI would create.

    Extracted so unit tests can assert the shape without running a Temporal
    client against a live cluster.
    """
    return Schedule(
        action=ScheduleActionStartWorkflow(
            "RetentionSweepWorkflow",
            args=[dry_run],
            id=_WORKFLOW_ID,
            task_queue=task_queue,
            execution_timeout=timedelta(minutes=30),
        ),
        spec=ScheduleSpec(cron_expressions=[cron]),
        state=ScheduleState(paused=paused),
    )


async def _async_main(args: argparse.Namespace) -> None:
    settings = get_settings()
    client = await connect_temporal(settings)

    schedule = build_schedule(
        task_queue=settings.temporal_task_queue,
        cron=args.cron,
        dry_run=args.dry_run,
        paused=args.paused,
    )

    try:
        await client.create_schedule(args.schedule_id, schedule)
        LOGGER.info("created schedule %s cron=%r", args.schedule_id, args.cron)
        return
    except ScheduleAlreadyRunningError:
        pass

    handle = client.get_schedule_handle(args.schedule_id)

    async def _update(input: ScheduleUpdateInput) -> ScheduleUpdate:
        del input
        return ScheduleUpdate(schedule=schedule)

    await handle.update(_update)
    LOGGER.info("updated schedule %s cron=%r", args.schedule_id, args.cron)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(_async_main(parse_args()))


if __name__ == "__main__":  # pragma: no cover - script entry
    main()
