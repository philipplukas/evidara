from __future__ import annotations

from platform_control.config import Settings, get_settings
from platform_control.events.publisher import (
    LocalOutboxRawArtifactPublisher,
    NatsRawArtifactPublisher,
    NoopRawArtifactPublisher,
    PubSubRawArtifactPublisher,
    RawArtifactPublisher,
)
from platform_control.services.artifact_store import (
    ArtifactStore,
    GcsArtifactStore,
    LocalArtifactStore,
    S3ArtifactStore,
)


def get_artifact_store(settings: Settings | None = None) -> ArtifactStore:
    active_settings = settings or get_settings()
    if active_settings.artifact_store_backend == "gcs":
        return GcsArtifactStore(
            bucket_name=active_settings.raw_artifact_bucket,
            object_prefix=active_settings.raw_artifact_prefix,
            project_id=active_settings.gcp_project_id,
        )
    if active_settings.artifact_store_backend == "s3":
        return S3ArtifactStore(
            bucket_name=active_settings.raw_artifact_bucket,
            object_prefix=active_settings.raw_artifact_prefix,
            endpoint_url=active_settings.s3_endpoint_url,
            region_name=active_settings.s3_region,
            access_key_id=active_settings.s3_access_key_id,
            secret_access_key=active_settings.s3_secret_access_key,
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
    if active_settings.event_publisher_backend == "nats":
        return NatsRawArtifactPublisher(
            servers=active_settings.nats_servers,
            raw_artifact_subject=active_settings.nats_raw_artifact_subject,
            artifact_bundle_subject=active_settings.nats_artifact_bundle_subject,
        )
    if active_settings.event_publisher_backend == "local_outbox":
        return LocalOutboxRawArtifactPublisher(base_dir=active_settings.raw_artifact_local_dir)
    return NoopRawArtifactPublisher()
