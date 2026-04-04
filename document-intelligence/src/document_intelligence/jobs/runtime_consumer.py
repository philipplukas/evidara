"""Always-on Pub/Sub consumer for artifact_bundle.available processing."""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import threading
import time
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from google.cloud import pubsub_v1

from document_intelligence.config.runtime import RuntimeSettings
from document_intelligence.contracts.envelope import EnvelopeError
from document_intelligence.events.publisher import (
    EventPublisherConfig,
    PubSubEventPublisher,
)
from document_intelligence.ingest.loaders import GcsBundleLoader
from document_intelligence.observability.event_logging import log_event
from document_intelligence.persist.sinks import (
    DeltaCanonicalSink,
    InMemoryCanonicalSink,
)
from document_intelligence.pipeline import DocumentProcessingPipeline

LOGGER = logging.getLogger("document_intelligence.runtime_consumer")

# Permanent failures are deterministic and message-content-driven:
# retrying the identical payload will produce the same error.
_PERMANENT_ERRORS = (EnvelopeError, json.JSONDecodeError, KeyError)


# ---------------------------------------------------------------------------
# Minimal HTTP health server for Cloud Run liveness / readiness probes.
# Runs in a daemon thread so it doesn't block the synchronous poll loop.
# ---------------------------------------------------------------------------


class _HealthHandler(BaseHTTPRequestHandler):
    """Return 200 on GET /health, 404 otherwise."""

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            body = json.dumps({"status": "ok", "service": "document-intelligence-consumer"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Silence default stderr logging to avoid noise."""


def _start_health_server() -> None:
    """Start the health HTTP server on $PORT (default 8080) in a daemon thread."""
    port = int(os.environ.get("PORT", "8080"))
    try:
        server = HTTPServer(("", port), _HealthHandler)
    except OSError as e:
        LOGGER.error("Failed to bind health server to port %d: %s", port, e)
        raise
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    LOGGER.info("Health server listening on port %d", port)


def _build_pipeline(
    environment: Mapping[str, str],
) -> tuple[DocumentProcessingPipeline, Any]:
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


def _extract_event_context(data: bytes) -> dict[str, str | None]:
    """Best-effort extraction of event context fields for logging."""
    try:
        payload = json.loads(data.decode("utf-8"))
        inner = payload.get("payload", {})
        provenance = inner.get("provenance", {}) if isinstance(inner, dict) else {}
        return {
            "correlation_id": payload.get("correlation_id"),
            "event_id": payload.get("event_id"),
            "event_type": payload.get("event_type"),
            "run_id": provenance.get("run_id") if isinstance(provenance, dict) else None,
        }
    except Exception:
        return {"correlation_id": None, "event_id": None, "event_type": None, "run_id": None}


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    _start_health_server()

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
            msg_id = received.message.message_id
            delivery_attempt = received.message.attributes.get("googclient_deliveryattempt", "unknown")
            ctx = _extract_event_context(received.message.data)
            start = time.monotonic()

            try:
                _process_message(received.message, pipeline, publisher)
                duration_ms = round((time.monotonic() - start) * 1000, 2)
                subscriber.acknowledge(
                    request={
                        "subscription": subscription_path,
                        "ack_ids": [received.ack_id],
                    }
                )
                log_event(
                    LOGGER,
                    logging.INFO,
                    "message_processed",
                    event_type=ctx["event_type"],
                    event_id=ctx["event_id"],
                    correlation_id=ctx["correlation_id"],
                    run_id=ctx["run_id"],
                    message_id=msg_id,
                    duration_ms=duration_ms,
                    subscription=args.subscription_name,
                )

            except _PERMANENT_ERRORS as exc:
                # Deterministic, message-content-driven — ack immediately,
                # do not waste retry budget or pollute DLQ.
                subscriber.acknowledge(
                    request={
                        "subscription": subscription_path,
                        "ack_ids": [received.ack_id],
                    }
                )
                log_event(
                    LOGGER,
                    logging.WARNING,
                    "message_rejected_permanent",
                    event_type=ctx["event_type"],
                    event_id=ctx["event_id"],
                    correlation_id=ctx["correlation_id"],
                    run_id=ctx["run_id"],
                    message_id=msg_id,
                    delivery_attempt=delivery_attempt,
                    error_class="permanent",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    subscription=args.subscription_name,
                )

            except Exception as exc:
                # Transient — do NOT ack.  Let ack deadline expire so
                # Pub/Sub retry_policy applies exponential backoff.
                # After max_delivery_attempts the message goes to DLQ.
                log_event(
                    LOGGER,
                    logging.ERROR,
                    "message_processing_failed",
                    event_type=ctx["event_type"],
                    event_id=ctx["event_id"],
                    correlation_id=ctx["correlation_id"],
                    run_id=ctx["run_id"],
                    message_id=msg_id,
                    delivery_attempt=delivery_attempt,
                    error_class="transient",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    subscription=args.subscription_name,
                )

    LOGGER.info("consumer stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
