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

    # Temporal validity (#628/#633). Providers that can establish a norm's
    # in-force window (fedlex_sparql from jolux applicability dates,
    # gemeinde_http from `inkrafttretendatum`) put it on the resource
    # metadata. Without these two hints the window dies here: DI's artifact
    # loader keeps only the body bytes, so every federal norm answered
    # `in_force_state: unknown` even though acquisition knew the answer.
    # Absent keys stay absent — an unknown window must never be guessed.
    for hint_key, metadata_key in (
        ("in_force_from_hint", "in_force_from"),
        ("in_force_until_hint", "in_force_until"),
    ):
        value = _extract_metadata_string(artifact_metadata, metadata_key)
        if value is not None:
            hints[hint_key] = value

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
    attribution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    captured_at = snapshot_captured_at or datetime.now(UTC)
    bundle_metadata_payload: dict[str, Any] = {"generated_by": "platform-control"}
    if bundle_metadata:
        bundle_metadata_payload.update(bundle_metadata)
    if attribution:
        bundle_metadata_payload["attribution"] = attribution
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

    for key in ("short_title", "title", "title_hint", "pageTitle", "page_title"):
        candidate = artifact_metadata.get(key)
        if isinstance(candidate, str):
            stripped = candidate.strip()
            if stripped and not _is_placeholder_title(stripped):
                return stripped

    for nested_key in ("metadata", "provider_metadata"):
        nested_metadata = artifact_metadata.get(nested_key)
        if not isinstance(nested_metadata, dict):
            continue
        nested_title = _extract_title_hint(nested_metadata)
        if nested_title is not None:
            return nested_title
    return None


def _extract_metadata_string(
    artifact_metadata: dict[str, Any] | None,
    key: str,
) -> str | None:
    """Read a non-empty string ``key`` from artifact or provider metadata.

    Mirrors ``_extract_title_hint``'s nesting: ``run_service`` attaches the
    provider's own payload under ``provider_metadata``, so a value set by the
    provider is one level down from the artifact metadata the manifest sees.
    """
    if not isinstance(artifact_metadata, dict):
        return None

    candidate = artifact_metadata.get(key)
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()

    for nested_key in ("metadata", "provider_metadata"):
        nested_metadata = artifact_metadata.get(nested_key)
        if not isinstance(nested_metadata, dict):
            continue
        nested_value = _extract_metadata_string(nested_metadata, key)
        if nested_value is not None:
            return nested_value
    return None


def _is_placeholder_title(title: str) -> bool:
    lower = title.strip().lower()
    if not lower:
        return True
    if lower in {"untitled document", "ris dokument"}:
        return True
    return lower.startswith("ris —") or lower.startswith("ris -")
