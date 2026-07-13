"""Outbound document publication event construction."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from document_intelligence.canonical.ids import random_prefixed_id
from document_intelligence.canonical.models import Document, ProcessingManifest
from document_intelligence.errors import ProcessingError
from document_intelligence.persist.surfaces import PUBLISHED_DOCUMENTS, PUBLISHED_SECTIONS

# A canonical document is "official" when its source origin is official. Kept in one place
# so the live pipeline and the Delta backfill classify a rebuilt document identically.
_OFFICIAL_SOURCE_ORIGIN_KINDS = frozenset({"official_primary", "official_mirror"})


def _optional_non_empty_str(value: Any) -> str | None:
    """Normalize optional string fields for downstream JSON Schema / Pydantic (empty string is not null)."""
    if value is None or not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _authority_name_from_metadata(metadata: Mapping[str, Any]) -> str | None:
    source_defaults = metadata.get("source_defaults")
    if not isinstance(source_defaults, Mapping):
        return None
    return _optional_non_empty_str(source_defaults.get("authority_name"))


def _is_official_from_metadata(metadata: Mapping[str, Any]) -> bool:
    return metadata.get("source_origin_kind") in _OFFICIAL_SOURCE_ORIGIN_KINDS


def _processing_manifest_ref(processing_manifest_id: str) -> dict[str, Any]:
    return {
        "manifest_id": processing_manifest_id,
        "manifest_type": "processing_manifest",
        "manifest_version": 1,
        "dataset_ref": {
            "surface_name": "processing_manifests",
            "surface_version": 1,
            "record_key": {"processing_manifest_id": processing_manifest_id},
        },
    }


def _envelope(
    payload: dict[str, Any],
    *,
    correlation_id: str | None,
    causation_id: str | None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "event_type": "document.processed",
        "event_version": 1,
        "event_id": random_prefixed_id("evt"),
        "occurred_at": _utc_now(),
        "producer": "document-intelligence",
        "payload": payload,
    }
    # The event envelope contract types these as strings, not nullable — a document with no
    # upstream correlation/causation must omit them rather than send an explicit null.
    if correlation_id is not None:
        event["correlation_id"] = correlation_id
    if causation_id is not None:
        event["causation_id"] = causation_id
    return event


def build_document_processed_event(
    *,
    document: Document,
    manifest: ProcessingManifest,
    correlation_id: str | None,
    causation_id: str | None,
) -> dict[str, Any]:
    metadata: Mapping[str, Any] = document.metadata if isinstance(document.metadata, Mapping) else {}
    payload = {
        "document_id": document.document_id,
        "document_revision": document.document_revision,
        "processing_manifest_id": manifest.processing_manifest_id,
        "processing_version": manifest.processing_version,
        "provenance": document.provenance.to_dict(),
        "authority_id": _optional_non_empty_str(document.authority_id),
        "authority_name": _authority_name_from_metadata(metadata),
        "is_official": _is_official_from_metadata(metadata),
        "lifecycle_status": document.lifecycle_status,
        "published_document_ref": dict(manifest.published_document_ref or {}),
        "published_sections_ref": dict(manifest.published_sections_ref or {}),
        "processing_manifest_ref": _processing_manifest_ref(manifest.processing_manifest_id),
    }
    if manifest.supersedes_processing_manifest_id is not None:
        payload["supersedes_processing_manifest_id"] = manifest.supersedes_processing_manifest_id

    return _envelope(payload, correlation_id=correlation_id, causation_id=causation_id)


def build_document_processed_event_from_published_row(
    row: Mapping[str, Any],
    *,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> dict[str, Any]:
    """Rebuild a ``document.processed`` event from a canonical ``published_documents`` row.

    ADR-0005 makes the search index a *derived* view of canonical Delta, so a lost or
    reversioned index must be rebuildable from Delta alone. This reconstructs the event the
    live pipeline would have emitted for an already-published document, using only columns
    that live on the ``published_documents`` surface:

    - ``published_document_ref`` / ``published_sections_ref`` are deterministic in
      ``(document_id, processing_manifest_id)``, so a contract-valid event needs no
      ``processing_manifests`` read.
    - ``authority_name`` / ``is_official`` are re-derived from the document's persisted
      ``metadata`` by the same helpers the live path uses.

    Raises :class:`ProcessingError` when the row cannot yield a valid event, so the backfill
    job can record the row as skipped instead of aborting the whole run.
    """
    document_id = _required_str(row, "document_id")
    processing_manifest_id = _required_str(row, "processing_manifest_id")

    provenance = row.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ProcessingError(
            "backfill_row_invalid",
            f"published document {document_id} is missing provenance",
        )

    revision = row.get("document_revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ProcessingError(
            "backfill_row_invalid",
            f"published document {document_id} has invalid document_revision {revision!r}",
        )

    metadata_value = row.get("metadata")
    metadata: Mapping[str, Any] = metadata_value if isinstance(metadata_value, Mapping) else {}

    payload: dict[str, Any] = {
        "document_id": document_id,
        "document_revision": revision,
        "processing_manifest_id": processing_manifest_id,
        "processing_version": _required_str(row, "processing_version"),
        "provenance": dict(provenance),
        "authority_id": _optional_non_empty_str(row.get("authority_id")),
        "authority_name": _authority_name_from_metadata(metadata),
        "is_official": _is_official_from_metadata(metadata),
        "lifecycle_status": _required_str(row, "lifecycle_status"),
        "published_document_ref": PUBLISHED_DOCUMENTS.dataset_ref(
            document_id=document_id,
            processing_manifest_id=processing_manifest_id,
        ),
        "published_sections_ref": PUBLISHED_SECTIONS.dataset_ref(
            document_id=document_id,
            processing_manifest_id=processing_manifest_id,
        ),
        "processing_manifest_ref": _processing_manifest_ref(processing_manifest_id),
    }

    # legal-search's projections DTO only accepts a run id as correlation_id; default to the
    # run that originally produced the document so a backfilled row stays traceable to it.
    resolved_correlation = correlation_id or _optional_non_empty_str(provenance.get("run_id"))
    return _envelope(payload, correlation_id=resolved_correlation, causation_id=causation_id)


def _required_str(row: Mapping[str, Any], field_name: str) -> str:
    value = _optional_non_empty_str(row.get(field_name))
    if value is None:
        raise ProcessingError(
            "backfill_row_invalid",
            f"published document row is missing {field_name}",
        )
    return value


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
