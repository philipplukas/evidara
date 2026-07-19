from __future__ import annotations

from datetime import datetime
from typing import Any

from platform_control.ids import generate_prefixed_id
from platform_control.models.raw_artifact import RawArtifact

# The acquisition envelope (`acquisition_core.normalization`) carries the document's
# own bytes inline so a JSON payload can hold them — text verbatim under `inline_body`,
# binary base64 under `inline_body_base64` (#590). Those fields belong in the *stored*
# envelope, never in the event.
_INLINE_BODY_FIELDS = ("inline_body", "inline_body_base64")


def _reference_only_metadata(artifact_metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    """Strip the inline document body out of the event's metadata (#707).

    The event is a *notification that an artifact exists*, not a transport for it.
    The artifact is already durably stored — `payload.storage_path` is the whole
    point of the field — and document-intelligence reads the body from storage, not
    from this event: `ingest/loaders.py` unwraps the envelope it fetched from S3.
    So the body in the event was pure duplication, and it made the event's size a
    function of the document's size.

    That coupling is what broke #707. NATS enforces a `max_payload` (1 MB by
    default); Swiss federal acts routinely exceed it — TSchV is 1.44 MB, so its
    event was 1.23 MB of base64 and the publish raised `MaxPayloadError`. Raising
    the broker limit only moves the ceiling: a consolidated code runs to tens of
    megabytes, and every broker has *some* limit. Publishing a reference removes
    the ceiling instead of relocating it — event size is now bounded by the
    metadata (URLs, title, checksum), independent of how large the act is.

    `inline_body_encoding` is deliberately kept: it is a few bytes and it tells a
    consumer how the envelope at `storage_path` carries its body. The explicit
    `inline_body_omitted` marker says the body's absence is by design rather than
    a provider that captured nothing — the #628 rule against substituting a
    plausible value for "I don't know", applied to our own event.
    """
    if not isinstance(artifact_metadata, dict):
        return artifact_metadata
    if not any(field in artifact_metadata for field in _INLINE_BODY_FIELDS):
        return artifact_metadata
    trimmed = {
        key: value for key, value in artifact_metadata.items() if key not in _INLINE_BODY_FIELDS
    }
    trimmed["inline_body_omitted"] = True
    return trimmed


def build_raw_artifact_event(
    artifact: RawArtifact,
    *,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    event_timestamp = timestamp or artifact.created_at
    return {
        "event_type": "raw_artifact.available",
        "event_version": 1,
        "event_id": generate_prefixed_id("evt"),
        "occurred_at": event_timestamp.isoformat(),
        "producer": "platform-control",
        "payload": {
            "artifact_id": artifact.artifact_id,
            "source_id": artifact.source_id,
            "source_version_id": artifact.source_version_id,
            "run_id": artifact.run_id,
            "storage_path": artifact.storage_path,
            "content_type": artifact.content_type,
            "created_at": artifact.created_at.isoformat(),
            "metadata": _reference_only_metadata(artifact.artifact_metadata),
        },
    }
