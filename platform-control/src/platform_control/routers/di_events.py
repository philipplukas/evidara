import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.exceptions import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.database import get_session
from platform_control.observability.event_logging import log_event
from platform_control.schemas.document_events import (
    DocumentProcessedEvent,
    DocumentWithdrawnEvent,
)
from platform_control.schemas.processing_status import (
    DocumentProcessingStatusUpdatedEvent,
    EventAcceptedResponse,
)
from platform_control.services.processing_status_service import ProcessingStatusService
from platform_control.web.pubsub_push import decode_pubsub_push_json

router = APIRouter(prefix="/v1/di/events", tags=["di-events"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]

LOGGER = logging.getLogger("platform_control.di_events")


@router.post(
    "/document-processing-status-updated",
    response_model=EventAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def receive_document_processing_status_updated(
    request: Request,
    session: SessionDep,
) -> EventAcceptedResponse:
    try:
        payload = decode_pubsub_push_json(await request.json())
        event = DocumentProcessingStatusUpdatedEvent.model_validate(payload)
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error.errors(include_url=False, include_context=False),
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    log_event(
        LOGGER,
        logging.INFO,
        "di_event_received",
        event_type=event.event_type,
        event_id=event.event_id,
        correlation_id=event.correlation_id,
        status=event.payload.status.value,
    )
    start = time.monotonic()
    service = ProcessingStatusService(session)
    outcome = await service.record_document_processing_status(event)
    duration_ms = round((time.monotonic() - start) * 1000, 2)
    log_event(
        LOGGER,
        logging.INFO if outcome == "inserted" else logging.WARNING,
        "processing_status_recorded",
        event_type=event.event_type,
        event_id=event.event_id,
        correlation_id=event.correlation_id,
        status=outcome,
        duration_ms=duration_ms,
    )
    return EventAcceptedResponse()


@router.post(
    "/document-processed",
    response_model=EventAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def receive_document_processed(
    request: Request,
    session: SessionDep,
) -> EventAcceptedResponse:
    try:
        payload = decode_pubsub_push_json(await request.json())
        event = DocumentProcessedEvent.model_validate(payload)
    except ValidationError as error:
        LOGGER.error(
            "document_processed_validation_failed errors=%s",
            error.errors(include_url=False, include_context=False),
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error.errors(include_url=False, include_context=False),
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    log_event(
        LOGGER,
        logging.INFO,
        "di_event_received",
        event_type=event.event_type,
        event_id=event.event_id,
        correlation_id=event.correlation_id,
        document_id=event.payload.document_id,
    )
    start = time.monotonic()
    service = ProcessingStatusService(session)
    outcome = await service.record_document_processed(event)
    duration_ms = round((time.monotonic() - start) * 1000, 2)
    log_event(
        LOGGER,
        logging.INFO if outcome == "inserted" else logging.WARNING,
        "document_lifecycle_recorded",
        event_type=event.event_type,
        event_id=event.event_id,
        correlation_id=event.correlation_id,
        document_id=event.payload.document_id,
        status=outcome,
        duration_ms=duration_ms,
    )
    return EventAcceptedResponse()


@router.post(
    "/document-withdrawn",
    response_model=EventAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def receive_document_withdrawn(
    request: Request,
    session: SessionDep,
) -> EventAcceptedResponse:
    try:
        payload = decode_pubsub_push_json(await request.json())
        event = DocumentWithdrawnEvent.model_validate(payload)
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error.errors(include_url=False, include_context=False),
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    log_event(
        LOGGER,
        logging.INFO,
        "di_event_received",
        event_type=event.event_type,
        event_id=event.event_id,
        correlation_id=event.correlation_id,
        document_id=event.payload.document_id,
    )
    start = time.monotonic()
    service = ProcessingStatusService(session)
    outcome = await service.record_document_withdrawn(event)
    duration_ms = round((time.monotonic() - start) * 1000, 2)
    log_event(
        LOGGER,
        logging.INFO if outcome == "inserted" else logging.WARNING,
        "document_lifecycle_recorded",
        event_type=event.event_type,
        event_id=event.event_id,
        correlation_id=event.correlation_id,
        document_id=event.payload.document_id,
        status=outcome,
        duration_ms=duration_ms,
    )
    return EventAcceptedResponse()
