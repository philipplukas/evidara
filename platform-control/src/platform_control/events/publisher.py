from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol

from google.cloud import pubsub_v1

from platform_control.errors import IntegrationConfigurationError
from platform_control.events.raw_artifact import build_raw_artifact_event
from platform_control.models.raw_artifact import RawArtifact


class RawArtifactPublisher(Protocol):
    async def publish_raw_artifact_available(self, artifact: RawArtifact) -> None: ...


class NoopRawArtifactPublisher:
    async def publish_raw_artifact_available(self, artifact: RawArtifact) -> None:
        del artifact


class PubSubRawArtifactPublisher:
    def __init__(
        self,
        *,
        topic_name: str,
        project_id: str | None = None,
        publisher_client: pubsub_v1.PublisherClient | Any | None = None,
    ) -> None:
        self.project_id = project_id
        self.topic_name = topic_name
        self.publisher_client = publisher_client or pubsub_v1.PublisherClient()
        self.topic_path = self._resolve_topic_path(topic_name, project_id)

    async def publish_raw_artifact_available(self, artifact: RawArtifact) -> None:
        event = build_raw_artifact_event(artifact)
        data = json.dumps(event, sort_keys=True).encode("utf-8")

        def _publish() -> str:
            future = self.publisher_client.publish(
                self.topic_path,
                data=data,
                event_type=event["event_type"],
                artifact_id=artifact.artifact_id,
                run_id=artifact.run_id,
                source_id=artifact.source_id,
                source_version_id=artifact.source_version_id,
            )
            return future.result(timeout=10)

        await asyncio.to_thread(_publish)

    @staticmethod
    def _resolve_topic_path(topic_name: str, project_id: str | None) -> str:
        if topic_name.startswith("projects/"):
            return topic_name
        if not project_id:
            raise IntegrationConfigurationError(
                "GCP project ID is required when Pub/Sub topic is not a full resource path."
            )
        return pubsub_v1.PublisherClient.topic_path(project_id, topic_name)
