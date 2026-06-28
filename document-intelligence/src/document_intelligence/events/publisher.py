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
