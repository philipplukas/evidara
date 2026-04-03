from __future__ import annotations

import pytest

from platform_control.config import Settings
from platform_control.errors import IntegrationConfigurationError
from platform_control.events.publisher import NoopRawArtifactPublisher, PubSubRawArtifactPublisher
from platform_control.integrations import get_raw_artifact_publisher


class FakePublisherClient:
    @staticmethod
    def topic_path(project_id: str, topic_name: str) -> str:
        return f"projects/{project_id}/topics/{topic_name}"


def test_get_raw_artifact_publisher_defaults_to_noop() -> None:
    settings = Settings()

    publisher = get_raw_artifact_publisher(settings)

    assert isinstance(publisher, NoopRawArtifactPublisher)


def test_get_raw_artifact_publisher_requires_project_for_short_topic_names() -> None:
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
