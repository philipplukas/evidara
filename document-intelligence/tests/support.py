import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


EVENT_ID = "evt_01jq7bz6b7npge5hr2eb9n74ba"
BUNDLE_MANIFEST_ID = "abm_01jq7ab8x4nm7m3qz3b8e9q2fk"
SOURCE_SNAPSHOT_ID = "snap_01jq7a7n3nbzj6sk7v95p9frz1"
SOURCE_ID = "src_01jq79xv3wdd6yr8q5bn0m3zfk"
SOURCE_VERSION_ID = "sv_01jq79zcskf4m3m4gm3t5s59xq"
RUN_ID = "run_01jq7a3s9b7j4dndd9sgv6pb9d"
ARTIFACT_ID = "art_01jq7af3f8qqc46zc6xvkf9y4x"
PUBSUB_MESSAGE_ID = "2070443601311540"


def storage_ref_for_path(path: str, content_type: str) -> Dict[str, Any]:
    payload = Path(path).read_bytes()
    return {
        "uri": "file://{path}".format(path=path),
        "content_type": content_type,
        "byte_size": len(payload),
        "checksum": hashlib.sha256(payload).hexdigest(),
        "checksum_algorithm": "sha256",
        "created_at": "2026-03-29T09:30:05Z",
    }


def build_bundle_event(manifest_path: str) -> Dict[str, Any]:
    return {
        "event_type": "artifact_bundle.available",
        "event_version": 1,
        "event_id": EVENT_ID,
        "occurred_at": "2026-03-29T09:30:06Z",
        "producer": "platform-control",
        "correlation_id": RUN_ID,
        "payload": {
            "bundle_manifest_id": BUNDLE_MANIFEST_ID,
            "source_snapshot_id": SOURCE_SNAPSHOT_ID,
            "provenance": {
                "tenant_id": "tenant_public",
                "corpus_id": "corpus_public_ch_federal_law",
                "scope_type": "global_public",
                "source_id": SOURCE_ID,
                "source_version_id": SOURCE_VERSION_ID,
                "run_id": RUN_ID,
                "source_snapshot_id": SOURCE_SNAPSHOT_ID,
                "bundle_manifest_id": BUNDLE_MANIFEST_ID,
            },
            "source_origin_kind": "official_primary",
            "trust_tier": "authoritative",
            "bundle_manifest_ref": {
                "manifest_id": BUNDLE_MANIFEST_ID,
                "manifest_type": "artifact_bundle_manifest",
                "manifest_version": 1,
                "storage_ref": storage_ref_for_path(manifest_path, "application/json"),
            },
        },
    }


def build_pubsub_push_envelope(event_payload: Dict[str, Any]) -> Dict[str, Any]:
    encoded_payload = base64.b64encode(
        json.dumps(event_payload, sort_keys=True).encode("utf-8")
    ).decode("ascii")
    return {
        "message": {
            "data": encoded_payload,
            "messageId": PUBSUB_MESSAGE_ID,
            "publishTime": "2026-04-03T09:30:06Z",
            "attributes": {
                "event_type": str(event_payload.get("event_type", "")),
            },
        },
        "subscription": "projects/evidara-dev/subscriptions/document-intelligence",
    }


def build_manifest_payload(
    artifact_path: str,
    *,
    artifact_role: str,
    content_type: str = "text/html",
    parser_hints: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "bundle_manifest_id": BUNDLE_MANIFEST_ID,
        "manifest_version": 1,
        "provenance": {
            "tenant_id": "tenant_public",
            "corpus_id": "corpus_public_ch_federal_law",
            "scope_type": "global_public",
            "source_id": SOURCE_ID,
            "source_version_id": SOURCE_VERSION_ID,
            "run_id": RUN_ID,
            "source_snapshot_id": SOURCE_SNAPSHOT_ID,
            "bundle_manifest_id": BUNDLE_MANIFEST_ID,
        },
        "source_snapshot_id": SOURCE_SNAPSHOT_ID,
        "snapshot_external_id": "fedlex:2024-03-01:sr-101",
        "upstream_locator": "https://www.fedlex.admin.ch/eli/cc/1999/404/de",
        "source_origin_kind": "official_primary",
        "trust_tier": "authoritative",
        "snapshot_captured_at": "2026-03-29T09:30:00Z",
        "source_defaults": {
            "jurisdiction_id": "jur_ch_federal",
            "authority_id": "auth_fedlex",
            "language_codes": ["de"],
            "document_type_hint": "statute",
        },
        "parser_hints": parser_hints
        or {
            "expected_modalities": ["html"],
            "expected_content_types": [content_type],
            "preferred_primary_artifact_roles": ["primary_document"],
            "ocr_expected": False,
            "attachment_policy": "ignore",
        },
        "di_overrides": {},
        "reference_context": {
            "reference_snapshot_policy": "latest_approved",
            "reference_snapshot_set_ref": None,
        },
        "artifacts": [
            {
                "artifact_id": ARTIFACT_ID,
                "artifact_role": artifact_role,
                "storage_ref": storage_ref_for_path(artifact_path, content_type),
            }
        ],
    }


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def replace_placeholders(value: Any, replacements: Dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {
            key: replace_placeholders(inner_value, replacements)
            for key, inner_value in value.items()
        }
    if isinstance(value, list):
        return [replace_placeholders(item, replacements) for item in value]
    if isinstance(value, str):
        output = value
        for placeholder, replacement in replacements.items():
            output = output.replace(placeholder, replacement)
        return output
    return value


def fixture_path(*parts: str) -> str:
    return os.path.join(os.path.dirname(__file__), *parts)
