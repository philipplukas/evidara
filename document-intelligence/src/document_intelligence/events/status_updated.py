"""Outbound processing status event construction."""

from datetime import UTC, datetime
from typing import Any

from document_intelligence.canonical.ids import random_prefixed_id
from document_intelligence.contracts.envelope import Provenance


def build_processing_status_event(
    *,
    processing_manifest_id: str,
    provenance: Provenance,
    processing_version: str,
    status: str,
    document_id: str | None,
    document_revision: int | None,
    correlation_id: str | None,
    causation_id: str | None,
    error_code: str | None = None,
    error_summary: str | None = None,
) -> dict[str, Any]:
    return {
        "event_type": "document.processing_status.updated",
        "event_version": 1,
        "event_id": random_prefixed_id("evt"),
        "occurred_at": _utc_now(),
        "producer": "document-intelligence",
        "correlation_id": correlation_id,
        "causation_id": causation_id,
        "payload": {
            "processing_manifest_id": processing_manifest_id,
            "document_id": document_id,
            "document_revision": document_revision,
            "provenance": provenance.to_dict(),
            "processing_version": processing_version,
            "status": status,
            "error_code": error_code,
            "error_summary": error_summary,
        },
    }


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
