import os
import sys
import unittest
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from document_intelligence.events.publisher import (
    EventPublisherConfig,
    PubSubEventPublisher,
)
from document_intelligence.validate.schema_validation import (
    load_contract_example,
    validate_instance_against_contract,
)


class _StubPublishFuture:
    def result(self) -> None:
        return None


class _StubPublisherClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes]] = []

    def publish(self, topic_path: str, payload: bytes):
        self.calls.append((topic_path, payload))
        return _StubPublishFuture()


class PubSubEventPublisherTests(unittest.TestCase):
    def test_publishes_status_and_processed_events(self) -> None:
        client = _StubPublisherClient()
        publisher = PubSubEventPublisher(
            EventPublisherConfig(
                project_id="evidara-dev",
                status_topic_name="document-processing-status-updated",
                processed_topic_name="document-processed",
            ),
            client=client,  # type: ignore[arg-type]
        )

        publisher.publish_status_event(
            {"event_type": "document.processing_status.updated"}
        )
        publisher.publish_document_processed_event({"event_type": "document.processed"})

        self.assertEqual(len(client.calls), 2)
        self.assertIn("document-processing-status-updated", client.calls[0][0])
        self.assertIn("document-processed", client.calls[1][0])

    def test_published_payloads_validate_against_event_contracts(self) -> None:
        client = _StubPublisherClient()
        publisher = PubSubEventPublisher(
            EventPublisherConfig(
                project_id="evidara-dev",
                status_topic_name="document-processing-status-updated",
                processed_topic_name="document-processed",
            ),
            client=client,  # type: ignore[arg-type]
        )

        status_event = load_contract_example("document-processing-status-updated.json")
        processed_event = load_contract_example("document-processed.json")

        publisher.publish_status_event(status_event)
        publisher.publish_document_processed_event(processed_event)

        published_status_payload = json.loads(client.calls[0][1].decode("utf-8"))
        published_processed_payload = json.loads(client.calls[1][1].decode("utf-8"))

        validate_instance_against_contract(
            published_status_payload,
            "events/document-processing-status-updated.schema.json",
        )
        validate_instance_against_contract(
            published_processed_payload,
            "events/document-processed.schema.json",
        )


if __name__ == "__main__":
    unittest.main()
