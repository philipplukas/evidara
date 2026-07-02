from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import pytest

from platform_control.config import Settings
from platform_control.errors import IntegrationConfigurationError
from platform_control.events.publisher import (
    LocalOutboxRawArtifactPublisher,
    NatsRawArtifactPublisher,
    NoopRawArtifactPublisher,
    PubSubRawArtifactPublisher,
)
from platform_control.integrations import get_raw_artifact_publisher
from platform_control.models.raw_artifact import RawArtifact


class FakePublisherClient:
    @staticmethod
    def topic_path(project_id: str, topic_name: str) -> str:
        return f"projects/{project_id}/topics/{topic_name}"


def test_get_raw_artifact_publisher_defaults_to_noop() -> None:
    settings = Settings()

    publisher = get_raw_artifact_publisher(settings)

    assert isinstance(publisher, NoopRawArtifactPublisher)


def test_get_raw_artifact_publisher_can_use_local_outbox(tmp_path) -> None:
    settings = Settings(event_publisher_backend="local_outbox", raw_artifact_local_dir=tmp_path)

    publisher = get_raw_artifact_publisher(settings)

    assert isinstance(publisher, LocalOutboxRawArtifactPublisher)
    assert publisher.outbox_dir == tmp_path / "event-outbox"


def test_get_raw_artifact_publisher_can_use_nats() -> None:
    settings = Settings(
        event_publisher_backend="nats",
        nats_servers="nats://broker:4222",
        nats_raw_artifact_subject="evidara.raw-artifact-available",
        nats_artifact_bundle_subject="evidara.artifact-bundle-available",
    )

    publisher = get_raw_artifact_publisher(settings)

    assert isinstance(publisher, NatsRawArtifactPublisher)
    assert publisher.servers == "nats://broker:4222"
    assert publisher.raw_artifact_subject == "evidara.raw-artifact-available"
    assert publisher.artifact_bundle_subject == "evidara.artifact-bundle-available"


def test_local_outbox_writes_raw_artifact_and_bundle_events(tmp_path) -> None:
    publisher = LocalOutboxRawArtifactPublisher(base_dir=tmp_path)
    created_at = datetime(2026, 4, 27, tzinfo=UTC)
    artifact = RawArtifact(
        artifact_id="art_01kq8000000000000000000000",
        source_id="src_01kq8000000000000000000000",
        source_version_id="sv_01kq8000000000000000000000",
        run_id="run_01kq8000000000000000000000",
        storage_path="file:///tmp/doc.html",
        content_type="text/html",
        artifact_metadata={"title": "Replay proof"},
        created_at=created_at,
    )
    bundle_event = {
        "event_type": "artifact_bundle.available",
        "event_version": 1,
        "event_id": "evt_01kq8000000000000000000001",
        "occurred_at": created_at.isoformat(),
        "producer": "platform-control",
        "payload": {
            "bundle_manifest_id": "abm_01kq8000000000000000000000",
            "source_snapshot_id": "snap_01kq8000000000000000000000",
            "provenance": {
                "run_id": artifact.run_id,
                "source_id": artifact.source_id,
                "source_version_id": artifact.source_version_id,
            },
        },
    }

    asyncio.run(publisher.publish_raw_artifact_available(artifact))
    asyncio.run(publisher.publish_artifact_bundle_available(bundle_event))

    raw_files = list((tmp_path / "event-outbox" / "raw-artifact-available").glob("*.json"))
    bundle_path = (
        tmp_path
        / "event-outbox"
        / "artifact-bundle-available"
        / "evt_01kq8000000000000000000001.json"
    )
    assert len(raw_files) == 1
    raw_event = json.loads(raw_files[0].read_text(encoding="utf-8"))
    assert raw_event["payload"]["artifact_id"] == artifact.artifact_id
    assert json.loads(bundle_path.read_text(encoding="utf-8")) == bundle_event


def test_local_outbox_rejects_unsafe_event_ids(tmp_path) -> None:
    publisher = LocalOutboxRawArtifactPublisher(base_dir=tmp_path)

    with pytest.raises(ValueError, match="unsafe outbox event_id"):
        asyncio.run(
            publisher.publish_artifact_bundle_available(
                {
                    "event_type": "artifact_bundle.available",
                    "event_id": "../evt_01kq8000000000000000000000",
                }
            )
        )


def test_get_raw_artifact_publisher_requires_project_for_short_topic_names(monkeypatch) -> None:
    monkeypatch.setattr(
        "platform_control.events.publisher.pubsub_v1.PublisherClient",
        FakePublisherClient,
    )
    settings = Settings(
        event_publisher_backend="pubsub",
        gcp_project_id=None,
        raw_artifact_pubsub_topic="raw-artifact-available",
        artifact_bundle_pubsub_topic="artifact-bundle-available",
    )

    with pytest.raises(IntegrationConfigurationError):
        get_raw_artifact_publisher(settings)


def test_get_raw_artifact_publisher_accepts_full_topic_paths(monkeypatch) -> None:
    monkeypatch.setattr(
        "platform_control.events.publisher.pubsub_v1.PublisherClient",
        FakePublisherClient,
    )
    settings = Settings(
        event_publisher_backend="pubsub",
        gcp_project_id=None,
        raw_artifact_pubsub_topic="projects/evidara-dev/topics/raw-artifact-available",
        artifact_bundle_pubsub_topic="projects/evidara-dev/topics/artifact-bundle-available",
    )

    publisher = get_raw_artifact_publisher(settings)

    assert isinstance(publisher, PubSubRawArtifactPublisher)
    assert publisher.topic_path == "projects/evidara-dev/topics/raw-artifact-available"
    assert publisher.bundle_topic_path == "projects/evidara-dev/topics/artifact-bundle-available"
