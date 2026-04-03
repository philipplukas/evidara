"""Always-on Pub/Sub consumer for artifact_bundle.available processing."""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from collections.abc import Mapping
from typing import Any

from google.cloud import pubsub_v1

from document_intelligence.config.runtime import RuntimeSettings
from document_intelligence.events.publisher import (
    EventPublisherConfig,
    PubSubEventPublisher,
)
from document_intelligence.ingest.loaders import GcsBundleLoader
from document_intelligence.persist.sinks import DeltaCanonicalSink, InMemoryCanonicalSink
from document_intelligence.pipeline import DocumentProcessingPipeline

LOGGER = logging.getLogger("document_intelligence.runtime_consumer")


def _build_pipeline(environment: Mapping[str, str]) -> tuple[DocumentProcessingPipeline, Any]:
    settings = RuntimeSettings.from_mapping(environment)
    if settings.surface_uris is None:
        sink = InMemoryCanonicalSink()
    else:
        sink = DeltaCanonicalSink(settings.surface_uris.to_delta_sink_config())
    pipeline = DocumentProcessingPipeline(
        bundle_loader=GcsBundleLoader(),
        sink=sink,
        processing_version=settings.processing_version,
    )
    return pipeline, sink


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="document_intelligence_runtime_consumer",
        description="Continuously consume artifact_bundle.available from Pub/Sub.",
    )
    parser.add_argument("--project-id", required=True)
    parser.add_argument(
        "--subscription-name",
        default="document-intelligence-artifact-bundle-available",
    )
    parser.add_argument("--status-topic-name", default="document-processing-status-updated")
    parser.add_argument("--processed-topic-name", default="document-processed")
    parser.add_argument("--idle-sleep-seconds", type=float, default=1.0)
    parser.add_argument("--max-messages", type=int, default=10)
    parser.add_argument("--dry-run-publish", action="store_true")
    return parser.parse_args(argv)


def _process_message(
    message: pubsub_v1.types.PubsubMessage,
    pipeline: DocumentProcessingPipeline,
    publisher: PubSubEventPublisher | None,
) -> None:
    payload = json.loads(message.data.decode("utf-8"))
    result = pipeline.process_event(payload)
    if publisher is not None:
        for status_event in result.status_events:
            publisher.publish_status_event(status_event)
        publisher.publish_document_processed_event(result.document_processed_event)
def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    pipeline, _ = _build_pipeline(os.environ)
    publisher = (
        None
        if args.dry_run_publish
        else PubSubEventPublisher(
            EventPublisherConfig(
                project_id=args.project_id,
                status_topic_name=args.status_topic_name,
                processed_topic_name=args.processed_topic_name,
            )
        )
    )

    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = pubsub_v1.SubscriberClient.subscription_path(
        args.project_id,
        args.subscription_name,
    )

    should_stop = False

    def _handle_stop(_sig: int, _frame: Any) -> None:
        nonlocal should_stop
        should_stop = True

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    LOGGER.info("starting runtime consumer on %s", subscription_path)
    while not should_stop:
        response = subscriber.pull(
            request={
                "subscription": subscription_path,
                "max_messages": args.max_messages,
            }
        )
        if not response.received_messages:
            time.sleep(args.idle_sleep_seconds)
            continue

        for received in response.received_messages:
            try:
                _process_message(received.message, pipeline, publisher)
                subscriber.acknowledge(
                    request={
                        "subscription": subscription_path,
                        "ack_ids": [received.ack_id],
                    }
                )
            except Exception:
                LOGGER.exception("failed to process message %s", received.message.message_id)
                subscriber.modify_ack_deadline(
                    request={
                        "subscription": subscription_path,
                        "ack_ids": [received.ack_id],
                        "ack_deadline_seconds": 0,
                    }
                )

    LOGGER.info("consumer stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
