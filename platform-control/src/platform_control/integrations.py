from __future__ import annotations

from platform_control.config import Settings, get_settings
from platform_control.events.publisher import (
    LocalOutboxRawArtifactPublisher,
    NoopRawArtifactPublisher,
    PubSubRawArtifactPublisher,
    RawArtifactPublisher,
)
from platform_control.services.artifact_store import (
    ArtifactStore,
    GcsArtifactStore,
    LocalArtifactStore,
)


def get_artifact_store(settings: Settings | None = None) -> ArtifactStore:
    active_settings = settings or get_settings()
    if active_settings.artifact_store_backend == "gcs":
        return GcsArtifactStore(
            bucket_name=active_settings.raw_artifact_bucket,
            object_prefix=active_settings.raw_artifact_prefix,
            project_id=active_settings.gcp_project_id,
        )
    return LocalArtifactStore(base_dir=active_settings.raw_artifact_local_dir)


def get_raw_artifact_publisher(settings: Settings | None = None) -> RawArtifactPublisher:
    active_settings = settings or get_settings()
    if active_settings.event_publisher_backend == "pubsub":
        return PubSubRawArtifactPublisher(
            topic_name=active_settings.raw_artifact_pubsub_topic,
            bundle_topic_name=active_settings.artifact_bundle_pubsub_topic,
            project_id=active_settings.gcp_project_id,
        )
    if active_settings.event_publisher_backend == "local_outbox":
        return LocalOutboxRawArtifactPublisher(base_dir=active_settings.raw_artifact_local_dir)
    return NoopRawArtifactPublisher()
