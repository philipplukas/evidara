"""Service that aggregates run, processing-status, and document-lifecycle data into a timeline."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.errors import NotFoundError
from platform_control.models.document_lifecycle_event import DocumentLifecycleEvent
from platform_control.models.processing_status_update import ProcessingStatusUpdate
from platform_control.models.run import Run
from platform_control.schemas.lifecycle import (
    RunLifecycleCounts,
    RunLifecycleResponse,
    TimelineEntry,
    TimelineEntryKind,
)


class RunLifecycleService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_lifecycle(self, run_id: str) -> RunLifecycleResponse:
        run = await self.session.get(Run, run_id)
        if run is None:
            raise NotFoundError(f"Run not found: {run_id}")

        status_updates = await self._fetch_processing_status(run_id)
        lifecycle_events = await self._fetch_document_lifecycle(run_id)

        timeline: list[TimelineEntry] = []

        # Run start entry
        timeline.append(
            TimelineEntry(
                kind=TimelineEntryKind.RUN,
                occurred_at=run.started_at or run.created_at,
                summary=f"Run {run.status.value} (mode={run.mode.value})",
                status=run.status.value,
            )
        )

        # Run completion entry (if completed)
        if run.completed_at:
            summary = f"Run completed: {run.status.value}"
            if run.failure_reason:
                summary += f" — {run.failure_reason}"
            timeline.append(
                TimelineEntry(
                    kind=TimelineEntryKind.RUN,
                    occurred_at=run.completed_at,
                    summary=summary,
                    status=run.status.value,
                    error_summary=run.failure_reason,
                )
            )

        for psu in status_updates:
            timeline.append(
                TimelineEntry(
                    kind=TimelineEntryKind.PROCESSING_STATUS,
                    event_id=psu.event_id,
                    occurred_at=psu.occurred_at,
                    summary=f"Processing status: {psu.status.value}",
                    processing_manifest_id=psu.processing_manifest_id,
                    processing_version=psu.processing_version,
                    status=psu.status.value,
                    document_id=psu.document_id,
                    document_revision=psu.document_revision,
                    error_code=psu.error_code,
                    error_summary=psu.error_summary,
                )
            )

        for dle in lifecycle_events:
            summary = f"Document lifecycle: {dle.event_type}"
            if dle.lifecycle_status:
                summary += f" ({dle.lifecycle_status})"
            elif dle.reason_code:
                summary += f" ({dle.reason_code})"
            timeline.append(
                TimelineEntry(
                    kind=TimelineEntryKind.DOCUMENT_LIFECYCLE,
                    event_id=dle.event_id,
                    occurred_at=dle.occurred_at,
                    summary=summary,
                    event_type=dle.event_type,
                    processing_manifest_id=dle.processing_manifest_id,
                    processing_version=dle.processing_version,
                    document_id=dle.document_id,
                    document_revision=dle.document_revision,
                    lifecycle_status=dle.lifecycle_status,
                    reason_code=dle.reason_code,
                    reason_summary=dle.reason_summary,
                    search_disposition=dle.search_disposition,
                )
            )

        # Sort timeline chronologically
        timeline.sort(key=lambda e: e.occurred_at)

        return RunLifecycleResponse(
            run_id=run.run_id,
            source_id=run.source_id,
            source_version_id=run.source_version_id,
            run_status=run.status.value,
            started_at=run.started_at,
            completed_at=run.completed_at,
            timeline=timeline,
            counts=RunLifecycleCounts(
                processing_status_updates=len(status_updates),
                document_lifecycle_events=len(lifecycle_events),
            ),
        )

    async def _fetch_processing_status(self, run_id: str) -> list[ProcessingStatusUpdate]:
        result = await self.session.scalars(
            select(ProcessingStatusUpdate)
            .where(ProcessingStatusUpdate.run_id == run_id)
            .order_by(ProcessingStatusUpdate.occurred_at)
        )
        return list(result)

    async def _fetch_document_lifecycle(self, run_id: str) -> list[DocumentLifecycleEvent]:
        result = await self.session.scalars(
            select(DocumentLifecycleEvent)
            .where(DocumentLifecycleEvent.run_id == run_id)
            .order_by(DocumentLifecycleEvent.occurred_at)
        )
        return list(result)
