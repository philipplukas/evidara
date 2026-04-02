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
    async def publish_artifact_bundle_available(self, event: dict[str, Any]) -> None: ...


class NoopRawArtifactPublisher:
    async def publish_raw_artifact_available(self, artifact: RawArtifact) -> None:
        del artifact

    async def publish_artifact_bundle_available(self, event: dict[str, Any]) -> None:
        del event


class PubSubRawArtifactPublisher:
    def __init__(
        self,
        *,
        topic_name: str,
        bundle_topic_name: str,
        project_id: str | None = None,
        publisher_client: pubsub_v1.PublisherClient | Any | None = None,
    ) -> None:
        self.project_id = project_id
        self.topic_name = topic_name
        self.bundle_topic_name = bundle_topic_name
        self.publisher_client = publisher_client or pubsub_v1.PublisherClient()
        self.topic_path = self._resolve_topic_path(topic_name, project_id)
        self.bundle_topic_path = self._resolve_topic_path(bundle_topic_name, project_id)

    async def publish_raw_artifact_available(self, artifact: RawArtifact) -> None:
        event = build_raw_artifact_event(artifact)
        await self._publish(
            topic_path=self.topic_path,
            event=event,
            attributes={
                "event_type": event["event_type"],
                "artifact_id": artifact.artifact_id,
                "run_id": artifact.run_id,
                "source_id": artifact.source_id,
                "source_version_id": artifact.source_version_id,
            },
        )

    async def publish_artifact_bundle_available(self, event: dict[str, Any]) -> None:
        payload = event["payload"]
        provenance = payload["provenance"]
        await self._publish(
            topic_path=self.bundle_topic_path,
            event=event,
            attributes={
                "event_type": event["event_type"],
                "bundle_manifest_id": payload["bundle_manifest_id"],
                "source_snapshot_id": payload["source_snapshot_id"],
                "run_id": provenance["run_id"],
                "source_id": provenance["source_id"],
                "source_version_id": provenance["source_version_id"],
            },
        )

    async def _publish(
        self,
        *,
        topic_path: str,
        event: dict[str, Any],
        attributes: dict[str, str],
    ) -> None:
        data = json.dumps(event, sort_keys=True).encode("utf-8")

        def _publish_sync() -> str:
            future = self.publisher_client.publish(topic_path, data=data, **attributes)
            return future.result(timeout=10)

        await asyncio.to_thread(_publish_sync)

    @staticmethod
    def _resolve_topic_path(topic_name: str, project_id: str | None) -> str:
        if topic_name.startswith("projects/"):
            return topic_name
        if not project_id:
            raise IntegrationConfigurationError(
                "GCP project ID is required when Pub/Sub topic is not a full resource path."
            )
        return pubsub_v1.PublisherClient.topic_path(project_id, topic_name)
