"""Outbound processing status event construction."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from document_intelligence.canonical.ids import random_prefixed_id
from document_intelligence.contracts.envelope import Provenance


def build_processing_status_event(
    *,
    processing_manifest_id: str,
    provenance: Provenance,
    processing_version: str,
    status: str,
    document_id: Optional[str],
    document_revision: Optional[int],
    correlation_id: Optional[str],
    causation_id: Optional[str],
    error_code: Optional[str] = None,
    error_summary: Optional[str] = None,
) -> Dict[str, Any]:
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
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
