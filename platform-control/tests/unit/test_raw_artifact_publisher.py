from __future__ import annotations

from datetime import UTC, datetime

import pytest

from platform_control.events.publisher import PubSubRawArtifactPublisher
from platform_control.models.raw_artifact import RawArtifact


class FakePublishFuture:
    def result(self, timeout: int | None = None) -> str:
        del timeout
        return "message-123"


class FakePublisherClient:
    def __init__(self) -> None:
        self.published: list[tuple[str, bytes, dict[str, str]]] = []

    def publish(self, topic_path: str, data: bytes, **attributes: str) -> FakePublishFuture:
        self.published.append((topic_path, data, attributes))
        return FakePublishFuture()


@pytest.mark.asyncio
async def test_pubsub_publisher_builds_raw_artifact_event() -> None:
    publisher_client = FakePublisherClient()
    publisher = PubSubRawArtifactPublisher(
        topic_name="projects/test-project/topics/raw-artifact-available",
        bundle_topic_name="projects/test-project/topics/artifact-bundle-available",
        publisher_client=publisher_client,
    )
    artifact = RawArtifact(
        artifact_id="art_123",
        run_id="run_123",
        source_id="src_123",
        source_version_id="sv_123",
        storage_path="gs://bucket/runs/run_123/art_123.json",
        content_type="text/html",
        artifact_metadata={"page": 1},
        created_at=datetime(2026, 3, 29, 12, 0, tzinfo=UTC),
    )

    await publisher.publish_raw_artifact_available(artifact)

    topic_path, data, attributes = publisher_client.published[0]
    assert topic_path == "projects/test-project/topics/raw-artifact-available"
    assert attributes["event_type"] == "raw_artifact.available"
    assert attributes["artifact_id"] == "art_123"
    assert b'"event_type": "raw_artifact.available"' in data
    assert b'"storage_path": "gs://bucket/runs/run_123/art_123.json"' in data


@pytest.mark.asyncio
async def test_pubsub_publisher_builds_artifact_bundle_event() -> None:
    publisher_client = FakePublisherClient()
    publisher = PubSubRawArtifactPublisher(
        topic_name="projects/test-project/topics/raw-artifact-available",
        bundle_topic_name="projects/test-project/topics/artifact-bundle-available",
        publisher_client=publisher_client,
    )

    await publisher.publish_artifact_bundle_available(
        {
            "event_type": "artifact_bundle.available",
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

    topic_path, data, attributes = publisher_client.published[0]
    assert topic_path == "projects/test-project/topics/artifact-bundle-available"
    assert attributes["event_type"] == "artifact_bundle.available"
    assert attributes["bundle_manifest_id"] == "abm_123"
    assert b'"event_type": "artifact_bundle.available"' in data
