"""Publish document-intelligence outbound events (status + document.processed)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from google.cloud import pubsub_v1


@runtime_checkable
class EventPublisher(Protocol):
    """Outbound publisher port for DI status / document.processed events.

    Lets the runtime depend on the capability rather than the Pub/Sub SDK, so a
    self-hosted broker (NATS JetStream, ADR-0029) can be dropped in. The NATS
    implementation lands with the consumer rewrite (ADR-0029 Slice 3), where the
    async broker context is natural; the publish surface is typed against this
    Protocol now so that change needs no call-site churn.
    """

    def publish_status_event(self, event: dict[str, Any]) -> None: ...
    def publish_document_processed_event(self, event: dict[str, Any]) -> None: ...


@dataclass(frozen=True)
class EventPublisherConfig:
    project_id: str
    status_topic_name: str = "document-processing-status-updated"
    processed_topic_name: str = "document-processed"


class PubSubEventPublisher:
    def __init__(
        self,
        config: EventPublisherConfig,
        *,
        client: pubsub_v1.PublisherClient | None = None,
    ) -> None:
        self._config = config
        self._client = client or pubsub_v1.PublisherClient()

    def publish_status_event(self, event: dict[str, Any]) -> None:
        self._publish(self._config.status_topic_name, event)

    def publish_document_processed_event(self, event: dict[str, Any]) -> None:
        self._publish(self._config.processed_topic_name, event)

    def _publish(self, topic_name: str, event: dict[str, Any]) -> None:
        topic_path = pubsub_v1.PublisherClient.topic_path(
            self._config.project_id,
            topic_name,
        )
        payload = json.dumps(event, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self._client.publish(topic_path, payload).result()


@runtime_checkable
class AsyncEventPublisher(Protocol):
    """Async counterpart to EventPublisher for broker clients that are async-native.

    The NATS JetStream consumer (ADR-0029) runs in an event loop, so its publisher
    is async rather than blocking on a future like the Pub/Sub path.
    """

    async def publish_status_event(self, event: dict[str, Any]) -> None: ...
    async def publish_document_processed_event(self, event: dict[str, Any]) -> None: ...


@dataclass(frozen=True)
class NatsEventPublisherConfig:
    status_subject: str = "evidara.document-processing-status-updated"
    processed_subject: str = "evidara.document-processed"


class NatsDocumentEventPublisher:
    """Publish DI status / document.processed events to NATS JetStream (ADR-0029).

    Self-hosted replacement for the Pub/Sub publisher. Dedup via the ``Nats-Msg-Id``
    header keyed on ``event_id`` makes republish-on-retry idempotent, mirroring the
    consumer's at-least-once delivery. The JetStream context is injected (the consumer
    owns the connection); a stream binding the configured subjects must exist.
    """

    def __init__(self, jetstream: Any, config: NatsEventPublisherConfig | None = None) -> None:
        self._jetstream = jetstream
        self._config = config or NatsEventPublisherConfig()

    async def publish_status_event(self, event: dict[str, Any]) -> None:
        await self._publish(self._config.status_subject, event)

    async def publish_document_processed_event(self, event: dict[str, Any]) -> None:
        await self._publish(self._config.processed_subject, event)

    async def _publish(self, subject: str, event: dict[str, Any]) -> None:
        payload = json.dumps(event, sort_keys=True, separators=(",", ":")).encode("utf-8")
        headers: dict[str, str] | None = None
        event_id = event.get("event_id")
        if isinstance(event_id, str) and event_id:
            headers = {"Nats-Msg-Id": event_id}
        await self._jetstream.publish(subject, payload, headers=headers)
