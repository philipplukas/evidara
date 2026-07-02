from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
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


class LocalOutboxRawArtifactPublisher:
    """Persist outbound events to a local outbox for GCP-free staging replay."""

    def __init__(self, *, base_dir: Path) -> None:
        self.outbox_dir = base_dir / "event-outbox"

    async def publish_raw_artifact_available(self, artifact: RawArtifact) -> None:
        event = build_raw_artifact_event(artifact)
        await self._write_event(stream="raw-artifact-available", event=event)

    async def publish_artifact_bundle_available(self, event: dict[str, Any]) -> None:
        await self._write_event(stream="artifact-bundle-available", event=event)

    async def _write_event(self, *, stream: str, event: dict[str, Any]) -> None:
        await asyncio.to_thread(self._write_event_sync, stream=stream, event=event)

    def _write_event_sync(self, *, stream: str, event: dict[str, Any]) -> None:
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("outbox event must include a non-empty event_id")
        if "/" in event_id or "\\" in event_id or event_id in {".", ".."}:
            raise ValueError(f"unsafe outbox event_id: {event_id!r}")

        root = self.outbox_dir.resolve(strict=False)
        stream_dir = (root / stream).resolve(strict=False)
        event_path = (stream_dir / f"{event_id}.json").resolve(strict=False)
        if root != event_path and root not in event_path.parents:
            raise ValueError(f"unsafe outbox path for event_id: {event_id!r}")

        stream_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = stream_dir / f".{event_id}.{uuid.uuid4().hex}.tmp"
        tmp_path.write_text(json.dumps(event, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp_path.replace(event_path)


class NatsRawArtifactPublisher:
    """Publish raw-artifact / artifact-bundle events to NATS JetStream.

    Self-hosted replacement for Pub/Sub (ADR-0029). JetStream provides at-least-once
    delivery plus publish dedup via the ``Nats-Msg-Id`` header (keyed on ``event_id``),
    mirroring the idempotency the Pub/Sub path relied on. The JetStream context can be
    injected for tests; otherwise a connection is opened lazily on first publish.

    A JetStream stream binding the configured subjects (e.g. ``evidara.>``) must exist
    in the broker; stream provisioning is a deployment concern (ADR-0029 Slice 5).
    """

    def __init__(
        self,
        *,
        servers: str,
        raw_artifact_subject: str,
        artifact_bundle_subject: str,
        jetstream: Any | None = None,
    ) -> None:
        self.servers = servers
        self.raw_artifact_subject = raw_artifact_subject
        self.artifact_bundle_subject = artifact_bundle_subject
        self._jetstream = jetstream
        self._connection: Any | None = None

    async def publish_raw_artifact_available(self, artifact: RawArtifact) -> None:
        event = build_raw_artifact_event(artifact)
        await self._publish(
            subject=self.raw_artifact_subject,
            event=event,
            headers={
                "event_type": str(event["event_type"]),
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
            subject=self.artifact_bundle_subject,
            event=event,
            headers={
                "event_type": str(event["event_type"]),
                "bundle_manifest_id": payload["bundle_manifest_id"],
                "source_snapshot_id": payload["source_snapshot_id"],
                "run_id": provenance["run_id"],
                "source_id": provenance["source_id"],
                "source_version_id": provenance["source_version_id"],
            },
        )

    async def _publish(
        self, *, subject: str, event: dict[str, Any], headers: dict[str, str]
    ) -> None:
        jetstream = await self._ensure_jetstream()
        data = json.dumps(event, sort_keys=True).encode("utf-8")
        event_id = event.get("event_id")
        msg_headers = dict(headers)
        if isinstance(event_id, str) and event_id:
            msg_headers["Nats-Msg-Id"] = event_id
        await jetstream.publish(subject, data, headers=msg_headers)

    async def _ensure_jetstream(self) -> Any:
        if self._jetstream is not None:
            return self._jetstream
        try:
            import nats
        except ModuleNotFoundError as exc:  # pragma: no cover - dependency guard
            raise IntegrationConfigurationError(
                "nats-py is required for the 'nats' event publisher backend."
            ) from exc
        self._connection = await nats.connect(self.servers)
        self._jetstream = self._connection.jetstream()
        return self._jetstream


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
