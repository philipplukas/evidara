from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.errors import NotFoundError
from platform_control.models.processing_status_update import ProcessingStatusUpdate
from platform_control.models.run import Run
from platform_control.schemas.processing_status import DocumentProcessingStatusUpdatedEvent


class ProcessingStatusService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record_document_processing_status(
        self,
        event: DocumentProcessingStatusUpdatedEvent,
    ) -> None:
        existing = await self.session.get(ProcessingStatusUpdate, event.event_id)
        if existing is not None:
            return

        payload = event.payload
        provenance = payload.provenance
        update = ProcessingStatusUpdate(
            event_id=event.event_id,
            run_id=provenance.run_id,
            processing_manifest_id=payload.processing_manifest_id,
            processing_version=payload.processing_version,
            status=payload.status,
            occurred_at=event.occurred_at,
            source_snapshot_id=provenance.source_snapshot_id,
            bundle_manifest_id=provenance.bundle_manifest_id,
            document_id=payload.document_id,
            document_revision=payload.document_revision,
            error_code=payload.error_code,
            error_summary=payload.error_summary,
        )
        self.session.add(update)
        await self.session.commit()

    async def list_run_processing_status(self, run_id: str) -> list[ProcessingStatusUpdate]:
        run = await self.session.get(Run, run_id)
        if run is None:
            raise NotFoundError(f"Run not found: {run_id}")

        result = await self.session.scalars(
            select(ProcessingStatusUpdate)
            .where(ProcessingStatusUpdate.run_id == run_id)
            .order_by(ProcessingStatusUpdate.occurred_at.desc())
        )
        return list(result)
