from __future__ import annotations

from datetime import datetime
from typing import Any

from platform_control.ids import generate_prefixed_id
from platform_control.models.raw_artifact import RawArtifact


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
            "metadata": artifact.artifact_metadata,
        },
    }
