"""Schedule evaluator — checks which schedules are due and creates runs."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.domain import ExecutionMode
from platform_control.models.run import Run
from platform_control.models.schedule import Schedule
from platform_control.models.source_version import SourceVersion

logger = logging.getLogger(__name__)


async def evaluate_due_schedules(session: AsyncSession) -> int:
    """Find schedules that are due and create runs for them.

    Schedules whose ``SourceVersion.execution_mode`` is ``OFF`` are skipped even
    when the cron expression is due; this is the operator-facing kill switch
    without having to disable the schedule row itself.

    Returns the number of runs created.
    """
    stmt = (
        select(Schedule)
        .join(SourceVersion, Schedule.source_version_id == SourceVersion.source_version_id)
        .where(Schedule.enabled.is_(True))
        .where(SourceVersion.execution_mode != ExecutionMode.OFF)
    )
    result = await session.execute(stmt)
    schedules = list(result.scalars().all())

    if not schedules:
        return 0

    now = datetime.now(UTC)
    created = 0

    for schedule in schedules:
        if _is_due(schedule, now):
            run = Run(
                source_id=schedule.source_id,
                source_version_id=schedule.source_version_id,
                mode=schedule.mode,
                run_metadata={
                    "scope": {"kind": "full_source"},
                    "triggered_by": "schedule",
                    "schedule_id": schedule.schedule_id,
                },
            )
            session.add(run)
            await session.flush()

            schedule.last_triggered_at = now
            schedule.last_run_id = run.run_id
            created += 1

            logger.info(
                "schedule_triggered",
                extra={
                    "extra_fields": {
                        "event": "schedule_triggered",
                        "schedule_id": schedule.schedule_id,
                        "run_id": run.run_id,
                        "source_id": schedule.source_id,
                        "cron": schedule.cron_expression,
                    }
                },
            )

    return created


def _is_due(schedule: Schedule, now: datetime) -> bool:
    """Check if a schedule's cron expression indicates it should fire."""
    try:
        cron = croniter(schedule.cron_expression, now)
        prev_fire = cron.get_prev(datetime)

        # If we've never triggered, or the previous fire time is after
        # our last trigger, then we're due.
        if schedule.last_triggered_at is None:
            return True

        return prev_fire > schedule.last_triggered_at
    except (ValueError, KeyError):
        logger.warning(
            "Invalid cron expression for schedule %s: %s",
            schedule.schedule_id,
            schedule.cron_expression,
        )
        return False
