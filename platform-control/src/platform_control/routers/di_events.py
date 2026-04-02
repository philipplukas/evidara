from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.database import get_session
from platform_control.schemas.processing_status import (
    DocumentProcessingStatusUpdatedEvent,
    EventAcceptedResponse,
)
from platform_control.services.processing_status_service import ProcessingStatusService

router = APIRouter(prefix="/v1/di/events", tags=["di-events"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post(
    "/document-processing-status-updated",
    response_model=EventAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def receive_document_processing_status_updated(
    event: DocumentProcessingStatusUpdatedEvent,
    session: SessionDep,
) -> EventAcceptedResponse:
    service = ProcessingStatusService(session)
    await service.record_document_processing_status(event)
    return EventAcceptedResponse()
