from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.database import get_session
from platform_control.schemas.errors import error_responses
from platform_control.schemas.schedule import (
    CreateScheduleRequest,
    ScheduleListResponse,
    ScheduleResponse,
    UpdateScheduleRequest,
)
from platform_control.services.schedule_service import ScheduleService

router = APIRouter(prefix="/v1/schedules", tags=["schedules"])

Session = Annotated[AsyncSession, Depends(get_session)]


@router.post("", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_schedule(request: CreateScheduleRequest, session: Session) -> ScheduleResponse:
    service = ScheduleService(session)
    return await service.create_schedule(request)


@router.get("", response_model=ScheduleListResponse)
async def list_schedules(
    session: Session,
    enabled_only: bool = Query(default=False),
) -> ScheduleListResponse:
    service = ScheduleService(session)
    return await service.list_schedules(enabled_only=enabled_only)


@router.get("/{schedule_id}", response_model=ScheduleResponse, responses=error_responses(404))
async def get_schedule(schedule_id: str, session: Session) -> ScheduleResponse:
    service = ScheduleService(session)
    return await service.get_schedule(schedule_id)


@router.patch("/{schedule_id}", response_model=ScheduleResponse, responses=error_responses(404))
async def update_schedule(
    schedule_id: str, request: UpdateScheduleRequest, session: Session
) -> ScheduleResponse:
    service = ScheduleService(session)
    return await service.update_schedule(schedule_id, request)


@router.delete(
    "/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(404),
)
async def delete_schedule(schedule_id: str, session: Session) -> None:
    service = ScheduleService(session)
    await service.delete_schedule(schedule_id)
