"""Lightweight contract validators aligned to the current repo schemas."""

import re
from typing import Any, Dict, Iterable, Mapping

from document_intelligence.canonical.models import Document, ProcessingManifest, Section
from document_intelligence.contracts.envelope import ManifestRef, Provenance, StorageObjectRef


_PATTERNS = {
    "document_id": re.compile(r"^doc_[0-9a-hjkmnp-tv-z]{26}$"),
    "section_id": re.compile(r"^sec_[0-9a-hjkmnp-tv-z]{26}$"),
    "processing_manifest_id": re.compile(r"^pm_[0-9a-hjkmnp-tv-z]{26}$"),
    "event_id": re.compile(r"^evt_[0-9a-hjkmnp-tv-z]{26}$"),
    "artifact_id": re.compile(r"^art_[0-9a-hjkmnp-tv-z]{26}$"),
}


def validate_document(document: Document) -> None:
    _require_pattern("document_id", document.document_id)
    _require_pattern("processing_manifest_id", document.processing_manifest_id)
    _require_pattern("artifact_id", document.primary_artifact_id)
    _require_non_empty(document.title, "document title")
    _require_non_empty(document.processed_at, "document processed_at")
    _require_non_empty(document.processing_version, "document processing_version")
    _require_non_empty(document.lifecycle_status, "document lifecycle_status")
    _require_non_empty(document.full_text, "document full_text")
    _require_non_empty(document.body_text, "document body_text")
    if document.document_revision < 1:
        raise ValueError("document revision must be >= 1")
    validate_provenance(document.provenance)


def validate_sections(sections: Iterable[Section]) -> None:
    for section in sections:
        _require_pattern("section_id", section.section_id)
        _require_pattern("document_id", section.document_id)
        _require_pattern("processing_manifest_id", section.processing_manifest_id)
        if section.document_revision < 1:
            raise ValueError("section document_revision must be >= 1")
        if section.ordinal < 0:
            raise ValueError("section ordinal must be >= 0")
        if section.depth < 0:
            raise ValueError("section depth must be >= 0")
        _require_non_empty(section.content, "section content")
        validate_provenance(section.provenance)


def validate_processing_manifest(manifest: ProcessingManifest) -> None:
    _require_pattern("processing_manifest_id", manifest.processing_manifest_id)
    _require_pattern("document_id", manifest.document_id)
    if manifest.manifest_version != 1:
        raise ValueError("processing manifest version must be 1")
    if manifest.document_revision < 1:
        raise ValueError("processing manifest document_revision must be >= 1")
    _require_non_empty(manifest.processing_version, "processing manifest processing_version")
    _require_non_empty(manifest.status, "processing manifest status")
    validate_provenance(manifest.provenance)
    validate_manifest_ref(manifest.input_bundle_manifest_ref)
    for key in [
        "source_profile_ref",
        "jurisdiction_profile_ref",
        "resolution_policy_ref",
    ]:
        _require_non_empty(
            manifest.selected_profiles.get(key),
            "selected_profiles.{key}".format(key=key),
        )
    if manifest.status == "canonical_ready":
        if not manifest.published_document_ref or not manifest.published_sections_ref:
            raise ValueError(
                "canonical_ready processing manifest requires published refs"
            )
        _require_non_empty(manifest.canonical_ready_at, "canonical_ready_at")
        validate_dataset_ref(manifest.published_document_ref, expect_key=True)
        validate_dataset_ref(manifest.published_sections_ref, expect_key=False)


def validate_event(event: Mapping[str, Any]) -> None:
    required_fields = [
        "event_type",
        "event_version",
        "event_id",
        "occurred_at",
        "producer",
        "payload",
    ]
    for field_name in required_fields:
        if event.get(field_name) is None:
            raise ValueError("event missing required field: {field}".format(field=field_name))
    _require_pattern("event_id", str(event["event_id"]))
    if not isinstance(event["payload"], Mapping):
        raise ValueError("event payload must be an object")


def validate_provenance(provenance: Provenance) -> None:
    _require_non_empty(provenance.tenant_id, "provenance tenant_id")
    _require_non_empty(provenance.corpus_id, "provenance corpus_id")
    _require_non_empty(provenance.scope_type, "provenance scope_type")
    _require_non_empty(provenance.source_id, "provenance source_id")
    _require_non_empty(provenance.source_version_id, "provenance source_version_id")
    _require_non_empty(provenance.run_id, "provenance run_id")


def validate_manifest_ref(manifest_ref: ManifestRef) -> None:
    _require_non_empty(manifest_ref.manifest_id, "manifest_ref manifest_id")
    _require_non_empty(manifest_ref.manifest_type, "manifest_ref manifest_type")
    if manifest_ref.manifest_version < 1:
        raise ValueError("manifest_ref manifest_version must be >= 1")
    if manifest_ref.storage_ref is None and manifest_ref.dataset_ref is None:
        raise ValueError("manifest_ref requires storage_ref or dataset_ref")
    if manifest_ref.storage_ref is not None:
        validate_storage_ref(manifest_ref.storage_ref)
    if manifest_ref.dataset_ref is not None:
        validate_dataset_ref(manifest_ref.dataset_ref, expect_key=True, allow_filter=True)


def validate_storage_ref(storage_ref: StorageObjectRef) -> None:
    _require_non_empty(storage_ref.uri, "storage_ref uri")
    _require_non_empty(storage_ref.content_type, "storage_ref content_type")
    _require_non_empty(storage_ref.checksum, "storage_ref checksum")
    _require_non_empty(storage_ref.checksum_algorithm, "storage_ref checksum_algorithm")
    if storage_ref.byte_size < 0:
        raise ValueError("storage_ref byte_size must be >= 0")


def validate_dataset_ref(
    dataset_ref: Mapping[str, Any],
    *,
    expect_key: bool,
    allow_filter: bool = False,
) -> None:
    _require_non_empty(dataset_ref.get("surface_name"), "dataset_ref surface_name")
    if int(dataset_ref.get("surface_version", 0)) < 1:
        raise ValueError("dataset_ref surface_version must be >= 1")
    has_key = isinstance(dataset_ref.get("record_key"), Mapping)
    has_filter = isinstance(dataset_ref.get("record_filter"), Mapping)
    if expect_key and not has_key:
        raise ValueError("dataset_ref requires record_key")
    if not expect_key and not has_filter and not (allow_filter and has_key):
        raise ValueError("dataset_ref requires record_filter")


def _require_non_empty(value: Any, name: str) -> None:
    if value is None:
        raise ValueError("{name} must be populated".format(name=name))
    if isinstance(value, str) and not value.strip():
        raise ValueError("{name} must be populated".format(name=name))


def _require_pattern(pattern_key: str, value: str) -> None:
    pattern = _PATTERNS[pattern_key]
    if not pattern.match(value):
        raise ValueError(
            "{pattern_key} does not match expected pattern: {value}".format(
                pattern_key=pattern_key, value=value
            )
        )
