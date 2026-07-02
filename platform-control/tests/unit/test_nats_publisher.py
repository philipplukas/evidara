from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from platform_control.events.publisher import NatsRawArtifactPublisher
from platform_control.models.raw_artifact import RawArtifact


class FakeJetStream:
    """Minimal stand-in for a nats JetStream context."""

    def __init__(self) -> None:
        self.published: list[tuple[str, bytes, dict[str, str] | None]] = []

    async def publish(
        self,
        subject: str,
        payload: bytes,
        headers: dict[str, str] | None = None,
    ) -> Any:
        self.published.append((subject, payload, headers))
        return None


def _publisher(jetstream: FakeJetStream) -> NatsRawArtifactPublisher:
    return NatsRawArtifactPublisher(
        servers="nats://test:4222",
        raw_artifact_subject="evidara.raw-artifact-available",
        artifact_bundle_subject="evidara.artifact-bundle-available",
        jetstream=jetstream,
    )


@pytest.mark.asyncio
async def test_nats_publisher_publishes_raw_artifact_event() -> None:
    jetstream = FakeJetStream()
    publisher = _publisher(jetstream)
    artifact = RawArtifact(
        artifact_id="art_123",
        run_id="run_123",
        source_id="src_123",
        source_version_id="sv_123",
        storage_path="s3://bucket/runs/run_123/art_123.json",
        content_type="text/html",
        artifact_metadata={"page": 1},
        created_at=datetime(2026, 3, 29, 12, 0, tzinfo=UTC),
    )

    await publisher.publish_raw_artifact_available(artifact)

    subject, payload, headers = jetstream.published[0]
    assert subject == "evidara.raw-artifact-available"
    assert headers is not None
    assert headers["event_type"] == "raw_artifact.available"
    assert headers["artifact_id"] == "art_123"
    event = json.loads(payload)
    assert event["event_type"] == "raw_artifact.available"
    # event_id drives JetStream publish dedup.
    assert headers["Nats-Msg-Id"] == event["event_id"]


@pytest.mark.asyncio
async def test_nats_publisher_publishes_artifact_bundle_event() -> None:
    jetstream = FakeJetStream()
    publisher = _publisher(jetstream)

    await publisher.publish_artifact_bundle_available(
        {
            "event_type": "artifact_bundle.available",
            "event_id": "evt_01kq8000000000000000000001",
            "payload": {
                "bundle_manifest_id": "abm_123",
                "source_snapshot_id": "snap_123",
                "provenance": {
                    "run_id": "run_123",
                    "source_id": "src_123",
                    "source_version_id": "sv_123",
                },
            },
        }
    )

    subject, payload, headers = jetstream.published[0]
    assert subject == "evidara.artifact-bundle-available"
    assert headers is not None
    assert headers["event_type"] == "artifact_bundle.available"
    assert headers["bundle_manifest_id"] == "abm_123"
    assert headers["Nats-Msg-Id"] == "evt_01kq8000000000000000000001"
    assert json.loads(payload)["event_type"] == "artifact_bundle.available"
