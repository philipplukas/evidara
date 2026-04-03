"""Outbound document publication event construction."""

from datetime import UTC, datetime
from typing import Any

from document_intelligence.canonical.ids import random_prefixed_id
from document_intelligence.canonical.models import Document, ProcessingManifest


def build_document_processed_event(
    *,
    document: Document,
    manifest: ProcessingManifest,
    correlation_id: str | None,
    causation_id: str | None,
) -> dict[str, Any]:
    payload = {
        "document_id": document.document_id,
        "document_revision": document.document_revision,
        "processing_manifest_id": manifest.processing_manifest_id,
        "processing_version": manifest.processing_version,
        "provenance": document.provenance.to_dict(),
        "lifecycle_status": document.lifecycle_status,
        "published_document_ref": dict(manifest.published_document_ref or {}),
        "published_sections_ref": dict(manifest.published_sections_ref or {}),
        "processing_manifest_ref": {
            "manifest_id": manifest.processing_manifest_id,
            "manifest_type": "processing_manifest",
            "manifest_version": 1,
            "dataset_ref": {
                "surface_name": "processing_manifests",
                "surface_version": 1,
                "record_key": {"processing_manifest_id": manifest.processing_manifest_id},
            },
        },
    }
    if manifest.supersedes_processing_manifest_id is not None:
        payload["supersedes_processing_manifest_id"] = manifest.supersedes_processing_manifest_id

    return {
        "event_type": "document.processed",
        "event_version": 1,
        "event_id": random_prefixed_id("evt"),
        "occurred_at": _utc_now(),
        "producer": "document-intelligence",
        "correlation_id": correlation_id,
        "causation_id": causation_id,
        "payload": payload,
    }


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
