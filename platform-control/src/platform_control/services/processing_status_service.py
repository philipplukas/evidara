from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.errors import NotFoundError
from platform_control.models.document_lifecycle_event import DocumentLifecycleEvent
from platform_control.models.processing_status_update import ProcessingStatusUpdate
from platform_control.models.run import Run
from platform_control.schemas.document_events import (
    DocumentProcessedEvent,
    DocumentWithdrawnEvent,
    PipelineStage,
)
from platform_control.schemas.processing_status import DocumentProcessingStatusUpdatedEvent


def _stages_for_storage(stages: list[PipelineStage]) -> list[dict] | None:
    """Serialise the stage ledger, mapping "no ledger" to NULL rather than `[]`.

    The payload's default is an empty list, which means the producer sent no
    ledger — an older document-intelligence, or a path that builds none. Storing
    that as `[]` would turn "we never recorded this" into "the pipeline ran no
    stages", and a reader has no way to tell the two apart afterwards. NULL keeps
    the distinction the column's docstring depends on.

    `exclude_none` so an unmeasured `items_in` is absent rather than `null`:
    absence is "not measured", and a rendered `0` would be a claim about the work.
    """
    if not stages:
        return None
    return [stage.model_dump(exclude_none=True) for stage in stages]


class ProcessingStatusService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record_document_processing_status(
        self,
        event: DocumentProcessingStatusUpdatedEvent,
    ) -> str:
        """Record a processing status update. Returns 'inserted' or 'duplicate'."""
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
        return await self._insert_idempotent(update)

    async def record_document_processed(self, event: DocumentProcessedEvent) -> str:
        """Record a document-processed lifecycle event. Returns 'inserted' or 'duplicate'."""
        payload = event.payload
        event_row = DocumentLifecycleEvent(
            event_id=event.event_id,
            event_type=event.event_type,
            run_id=payload.provenance.run_id,
            document_id=payload.document_id,
            document_revision=payload.document_revision,
            processing_manifest_id=payload.processing_manifest_id,
            processing_version=payload.processing_version,
            lifecycle_status=payload.lifecycle_status,
            reason_code=None,
            reason_summary=None,
            search_disposition=None,
            stages=_stages_for_storage(payload.stages),
            occurred_at=event.occurred_at,
        )
        return await self._insert_idempotent(event_row)

    async def record_document_withdrawn(self, event: DocumentWithdrawnEvent) -> str:
        """Record a document-withdrawn lifecycle event. Returns 'inserted' or 'duplicate'."""
        payload = event.payload
        event_row = DocumentLifecycleEvent(
            event_id=event.event_id,
            event_type=event.event_type,
            run_id=payload.provenance.run_id,
            document_id=payload.document_id,
            document_revision=payload.document_revision,
            processing_manifest_id=payload.processing_manifest_id,
            processing_version=None,
            lifecycle_status=None,
            reason_code=payload.reason_code,
            reason_summary=payload.reason_summary,
            search_disposition=payload.search_disposition,
            occurred_at=event.occurred_at,
        )
        return await self._insert_idempotent(event_row)

    async def list_run_processing_status(self, run_id: str) -> list[ProcessingStatusUpdate]:
        await self._ensure_run_exists(run_id)

        result = await self.session.scalars(
            select(ProcessingStatusUpdate)
            .where(ProcessingStatusUpdate.run_id == run_id)
            .order_by(ProcessingStatusUpdate.occurred_at.desc())
        )
        return list(result)

    async def list_run_document_lifecycle(self, run_id: str) -> list[DocumentLifecycleEvent]:
        await self._ensure_run_exists(run_id)

        result = await self.session.scalars(
            select(DocumentLifecycleEvent)
            .where(DocumentLifecycleEvent.run_id == run_id)
            .order_by(DocumentLifecycleEvent.occurred_at.desc())
        )
        return list(result)

    async def _ensure_run_exists(self, run_id: str) -> None:
        run = await self.session.get(Run, run_id)
        if run is None:
            raise NotFoundError(f"Run not found: {run_id}")

    async def _insert_idempotent(
        self,
        row: ProcessingStatusUpdate | DocumentLifecycleEvent,
    ) -> str:
        """Insert a row; return 'inserted' or 'duplicate' on PK conflict."""
        self.session.add(row)
        try:
            await self.session.commit()
            return "inserted"
        except IntegrityError:
            await self.session.rollback()
            return "duplicate"
