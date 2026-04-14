from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from platform_control.ids import generate_prefixed_id


def build_bundle_extraction_hints(
    *,
    artifact_metadata: dict[str, Any] | None = None,
    document_type_hint: str | None = None,
    authority_display_hint: str | None = None,
) -> dict[str, Any]:
    """Build a compact, DI-friendly hint payload for bundle metadata.

    The helper stays intentionally small and only copies hints we can derive
    from acquisition context already present at manifest creation time.
    Titles may be surfaced either directly on the artifact metadata or in the
    provider-owned metadata payload attached under ``provider_metadata``.
    """
    hints: dict[str, Any] = {}

    title_hint = _extract_title_hint(artifact_metadata)
    if title_hint is not None:
        hints["title_hint"] = title_hint

    if document_type_hint is not None:
        stripped = document_type_hint.strip()
        if stripped:
            hints["document_type_hint"] = stripped

    if authority_display_hint is not None:
        stripped = authority_display_hint.strip()
        if stripped:
            hints["authority_display_hint"] = stripped

    return hints


def build_artifact_bundle_manifest(
    *,
    bundle_manifest_id: str,
    source_snapshot_id: str,
    source_id: str,
    source_version_id: str,
    run_id: str,
    jurisdiction_id: str,
    authority_id: str | None,
    authority_name: str | None,
    upstream_locator: str,
    artifacts: list[dict[str, Any]],
    tenant_id: str = "tenant_public",
    corpus_id: str = "corpus_public_default",
    scope_type: str = "global_public",
    source_origin_kind: str = "official_primary",
    trust_tier: str = "authoritative",
    snapshot_external_id: str | None = None,
    language_codes: list[str] | None = None,
    document_type_hint: str | None = None,
    bundle_metadata: dict[str, Any] | None = None,
    snapshot_captured_at: datetime | None = None,
) -> dict[str, Any]:
    captured_at = snapshot_captured_at or datetime.now(UTC)
    bundle_metadata_payload: dict[str, Any] = {"generated_by": "platform-control"}
    if bundle_metadata:
        bundle_metadata_payload.update(bundle_metadata)
    return {
        "bundle_manifest_id": bundle_manifest_id,
        "manifest_version": 1,
        "provenance": {
            "tenant_id": tenant_id,
            "corpus_id": corpus_id,
            "scope_type": scope_type,
            "source_id": source_id,
            "source_version_id": source_version_id,
            "run_id": run_id,
            "source_snapshot_id": source_snapshot_id,
            "bundle_manifest_id": bundle_manifest_id,
        },
        "source_snapshot_id": source_snapshot_id,
        "snapshot_external_id": snapshot_external_id,
        "upstream_locator": upstream_locator,
        "source_origin_kind": source_origin_kind,
        "trust_tier": trust_tier,
        "snapshot_captured_at": captured_at.isoformat(),
        "source_defaults": {
            "jurisdiction_id": jurisdiction_id,
            "authority_id": authority_id,
            "authority_name": authority_name,
            "language_codes": language_codes or [],
            "document_type_hint": document_type_hint,
        },
        "parser_hints": {
            "expected_modalities": ["html"],
            "expected_content_types": sorted(
                {
                    content_type
                    for artifact in artifacts
                    if (content_type := artifact.get("storage_ref", {}).get("content_type"))
                }
            ),
            "preferred_primary_artifact_roles": ["primary_document"],
            "ocr_expected": False,
            "attachment_policy": "ingest_selected",
        },
        "reference_context": {
            "reference_snapshot_policy": "latest_approved",
            "reference_snapshot_set_ref": None,
        },
        "artifacts": artifacts,
        "bundle_metadata": bundle_metadata_payload,
    }


def build_artifact_bundle_available_event(
    *,
    bundle_manifest_id: str,
    source_snapshot_id: str,
    source_origin_kind: str,
    trust_tier: str,
    provenance: dict[str, Any],
    bundle_manifest_ref: dict[str, Any],
    correlation_id: str | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    timestamp = occurred_at or datetime.now(UTC)
    return {
        "event_type": "artifact_bundle.available",
        "event_version": 1,
        "event_id": generate_prefixed_id("evt"),
        "occurred_at": timestamp.isoformat(),
        "producer": "platform-control",
        "correlation_id": correlation_id,
        "payload": {
            "bundle_manifest_id": bundle_manifest_id,
            "source_snapshot_id": source_snapshot_id,
            "provenance": provenance,
            "source_origin_kind": source_origin_kind,
            "trust_tier": trust_tier,
            "bundle_manifest_ref": bundle_manifest_ref,
        },
    }


def _extract_title_hint(artifact_metadata: dict[str, Any] | None) -> str | None:
    if not isinstance(artifact_metadata, dict):
        return None

    for key in ("title", "title_hint", "pageTitle", "page_title"):
        candidate = artifact_metadata.get(key)
        if isinstance(candidate, str):
            stripped = candidate.strip()
            if stripped:
                return stripped

    for nested_key in ("metadata", "provider_metadata"):
        nested_metadata = artifact_metadata.get(nested_key)
        if not isinstance(nested_metadata, dict):
            continue
        nested_title = _extract_title_hint(nested_metadata)
        if nested_title is not None:
            return nested_title
    return None
