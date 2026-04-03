from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.errors import NotFoundError
from platform_control.models.schedule import Schedule
from platform_control.schemas.schedule import (
    CreateScheduleRequest,
    ScheduleListResponse,
    ScheduleResponse,
    UpdateScheduleRequest,
)

logger = logging.getLogger(__name__)


class ScheduleService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_schedule(self, request: CreateScheduleRequest) -> ScheduleResponse:
        schedule = Schedule(
            source_id=request.source_id,
            source_version_id=request.source_version_id,
            cron_expression=request.cron_expression,
            timezone=request.timezone,
            mode=request.mode,
            enabled=request.enabled,
            description=request.description,
        )
        self.session.add(schedule)
        await self.session.flush()
        await self.session.refresh(schedule)
        logger.info(
            "schedule_created",
            extra={
                "schedule_id": schedule.schedule_id,
                "source_id": schedule.source_id,
                "cron": schedule.cron_expression,
            },
        )
        return ScheduleResponse.model_validate(schedule)

    async def list_schedules(self, *, enabled_only: bool = False) -> ScheduleListResponse:
        stmt = select(Schedule).order_by(Schedule.created_at.desc())
        if enabled_only:
            stmt = stmt.where(Schedule.enabled.is_(True))
        result = await self.session.execute(stmt)
        schedules = list(result.scalars().all())
        return ScheduleListResponse(data=[ScheduleResponse.model_validate(s) for s in schedules])

    async def get_schedule(self, schedule_id: str) -> ScheduleResponse:
        schedule = await self._get_or_404(schedule_id)
        return ScheduleResponse.model_validate(schedule)

    async def update_schedule(
        self, schedule_id: str, request: UpdateScheduleRequest
    ) -> ScheduleResponse:
        schedule = await self._get_or_404(schedule_id)
        update_data = request.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(schedule, field, value)
        await self.session.flush()
        await self.session.refresh(schedule)
        logger.info(
            "schedule_updated",
            extra={
                "schedule_id": schedule.schedule_id,
                "fields": list(update_data.keys()),
            },
        )
        return ScheduleResponse.model_validate(schedule)

    async def delete_schedule(self, schedule_id: str) -> None:
        schedule = await self._get_or_404(schedule_id)
        await self.session.delete(schedule)
        await self.session.flush()
        logger.info(
            "schedule_deleted",
            extra={"schedule_id": schedule_id},
        )

    async def _get_or_404(self, schedule_id: str) -> Schedule:
        result = await self.session.execute(
            select(Schedule).where(Schedule.schedule_id == schedule_id)
        )
        schedule = result.scalar_one_or_none()
        if schedule is None:
            raise NotFoundError(f"Schedule {schedule_id} not found")
        return schedule
