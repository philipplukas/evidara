"""Always-on NATS JetStream consumer for artifact_bundle.available processing.

Self-hosted replacement for the Pub/Sub pull consumer (ADR-0029 Slice 3). Mirrors the
Pub/Sub delivery semantics:

- success            -> ``ack`` the message
- permanent error    -> ``term`` (drop; deterministic, content-driven — never retried)
- transient error    -> ``nak`` with backoff, until ``max_deliver`` attempts are exhausted
- exhausted transient -> publish the payload to the DLQ subject, then ``term``

The decision logic lives in :func:`dispatch_message`, which operates on an abstract
message interface so it is unit-testable without a live broker.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol

from document_intelligence.config.runtime import RuntimeSettings
from document_intelligence.events.publisher import (
    AsyncEventPublisher,
    NatsDocumentEventPublisher,
    NatsEventPublisherConfig,
)
from document_intelligence.ingest.loaders import DispatchingBundleLoader
from document_intelligence.jobs._consumer_common import (
    PERMANENT_ERRORS,
    extract_event_context,
    start_health_server,
)
from document_intelligence.observability.event_logging import log_event
from document_intelligence.observability.metrics import record_message_outcome
from document_intelligence.pipeline import ProcessingPipeline
from document_intelligence.processing_runtime import build_processing_pipeline

LOGGER = logging.getLogger("document_intelligence.nats_consumer")
CONSUMER_SERVICE = "document-intelligence-nats-consumer"


class IncomingMessage(Protocol):
    """Broker-agnostic view of a delivered message used by :func:`dispatch_message`."""

    @property
    def data(self) -> bytes: ...

    @property
    def num_delivered(self) -> int: ...

    async def ack(self) -> None: ...

    async def nak(self, delay: float | None = None) -> None: ...

    async def term(self) -> None: ...


async def dispatch_message(
    message: IncomingMessage,
    *,
    pipeline: ProcessingPipeline,
    publisher: AsyncEventPublisher | None,
    dlq_publish: Callable[[bytes], Awaitable[None]],
    max_deliver: int,
    nak_backoff_seconds: float,
    subject: str = "",
    logger: logging.Logger = LOGGER,
) -> str:
    """Process one message and ack/nak/term it. Returns the outcome label.

    Outcomes: ``processed`` | ``rejected_permanent`` | ``transient_retry`` | ``dead_lettered``.
    """
    ctx = extract_event_context(message.data)
    try:
        payload = json.loads(message.data.decode("utf-8"))
        result = pipeline.process_event(payload)
        if publisher is not None:
            for status_event in result.status_events:
                await publisher.publish_status_event(status_event)
            await publisher.publish_document_processed_event(result.document_processed_event)
        await message.ack()
        log_event(
            logger,
            logging.INFO,
            "message_processed",
            event_type=ctx["event_type"],
            event_id=ctx["event_id"],
            correlation_id=ctx["correlation_id"],
            run_id=ctx["run_id"],
            num_delivered=message.num_delivered,
            subject=subject,
        )
        return "processed"

    except PERMANENT_ERRORS as exc:
        # Deterministic, content-driven — drop without retry or DLQ.
        await message.term()
        log_event(
            logger,
            logging.WARNING,
            "message_rejected_permanent",
            event_type=ctx["event_type"],
            event_id=ctx["event_id"],
            correlation_id=ctx["correlation_id"],
            run_id=ctx["run_id"],
            num_delivered=message.num_delivered,
            error_class="permanent",
            error_type=type(exc).__name__,
            error_message=str(exc),
            subject=subject,
        )
        return "rejected_permanent"

    except Exception as exc:
        if message.num_delivered >= max_deliver:
            # Retry budget exhausted — route to DLQ, then stop redelivery.
            await dlq_publish(message.data)
            await message.term()
            log_event(
                logger,
                logging.ERROR,
                "message_dead_lettered",
                event_type=ctx["event_type"],
                event_id=ctx["event_id"],
                correlation_id=ctx["correlation_id"],
                run_id=ctx["run_id"],
                num_delivered=message.num_delivered,
                error_class="transient",
                error_type=type(exc).__name__,
                error_message=str(exc),
                subject=subject,
            )
            return "dead_lettered"

        # Transient — negative-ack with backoff so JetStream redelivers.
        await message.nak(delay=nak_backoff_seconds)
        log_event(
            logger,
            logging.ERROR,
            "message_processing_failed",
            event_type=ctx["event_type"],
            event_id=ctx["event_id"],
            correlation_id=ctx["correlation_id"],
            run_id=ctx["run_id"],
            num_delivered=message.num_delivered,
            error_class="transient",
            error_type=type(exc).__name__,
            error_message=str(exc),
            subject=subject,
        )
        return "transient_retry"


class _NatsMessage:
    """Adapt a nats.aio JetStream message to the IncomingMessage interface."""

    def __init__(self, msg: Any) -> None:
        self._msg = msg

    @property
    def data(self) -> bytes:
        return self._msg.data

    @property
    def num_delivered(self) -> int:
        return int(self._msg.metadata.num_delivered)

    async def ack(self) -> None:
        await self._msg.ack()

    async def nak(self, delay: float | None = None) -> None:
        await self._msg.nak(delay=delay)

    async def term(self) -> None:
        await self._msg.term()


def _build_pipeline(environment: Mapping[str, str]) -> ProcessingPipeline:
    settings = RuntimeSettings.from_mapping(environment)
    return build_processing_pipeline(
        runtime_settings=settings,
        bundle_loader=DispatchingBundleLoader(),
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="document_intelligence_nats_consumer",
        description="Continuously consume artifact_bundle.available from NATS JetStream.",
    )
    parser.add_argument("--servers", default="nats://localhost:4222")
    parser.add_argument("--stream", default="EVIDARA")
    parser.add_argument("--durable-name", default="di-artifact-bundle-available")
    parser.add_argument("--bundle-subject", default="evidara.artifact-bundle-available")
    parser.add_argument("--status-subject", default="evidara.document-processing-status-updated")
    parser.add_argument("--processed-subject", default="evidara.document-processed")
    parser.add_argument("--dlq-subject", default="evidara.artifact-bundle-available.dlq")
    parser.add_argument("--max-messages", type=int, default=10)
    parser.add_argument("--fetch-timeout-seconds", type=float, default=5.0)
    parser.add_argument("--max-deliver", type=int, default=5)
    parser.add_argument("--nak-backoff-seconds", type=float, default=5.0)
    parser.add_argument("--ack-wait-seconds", type=float, default=60.0)
    parser.add_argument("--dry-run-publish", action="store_true")
    return parser.parse_args(argv)


async def run(args: argparse.Namespace, environment: Mapping[str, str]) -> int:
    import nats
    from nats.js.api import AckPolicy, ConsumerConfig

    pipeline = _build_pipeline(environment)

    connection = await nats.connect(args.servers)
    jetstream = connection.jetstream()

    publisher: AsyncEventPublisher | None = (
        None
        if args.dry_run_publish
        else NatsDocumentEventPublisher(
            jetstream,
            NatsEventPublisherConfig(
                status_subject=args.status_subject,
                processed_subject=args.processed_subject,
            ),
        )
    )

    async def dlq_publish(data: bytes) -> None:
        await jetstream.publish(args.dlq_subject, data)

    # App-level DLQ owns the retry budget; set the JetStream ceiling above it as a
    # crash-loop backstop so the consumer (not the broker) decides when to dead-letter.
    consumer_config = ConsumerConfig(
        durable_name=args.durable_name,
        ack_policy=AckPolicy.EXPLICIT,
        ack_wait=args.ack_wait_seconds,
        max_deliver=args.max_deliver + 2,
        filter_subject=args.bundle_subject,
    )
    subscription = await jetstream.pull_subscribe(
        args.bundle_subject,
        durable=args.durable_name,
        stream=args.stream,
        config=consumer_config,
    )

    should_stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, should_stop.set)

    LOGGER.info("starting NATS consumer on %s (subject=%s)", args.stream, args.bundle_subject)
    while not should_stop.is_set():
        try:
            messages = await subscription.fetch(args.max_messages, timeout=args.fetch_timeout_seconds)
        except TimeoutError:
            # An idle fetch (no pending bundles within the timeout) is the normal
            # steady state, not an error — keep polling. nats-py 2.15's
            # PullSubscription.fetch raises the *builtin* TimeoutError; the earlier
            # `except nats.errors.TimeoutError` could not catch it (that class is a
            # *subclass* of builtin TimeoutError, and a subclass except never
            # catches a parent instance), so the bare timeout escaped and
            # crash-looped the consumer whenever the queue was empty. Catching the
            # builtin covers both the bare timeout and the nats subclass.
            continue
        for msg in messages:
            outcome = await dispatch_message(
                _NatsMessage(msg),
                pipeline=pipeline,
                publisher=publisher,
                dlq_publish=dlq_publish,
                max_deliver=args.max_deliver,
                nak_backoff_seconds=args.nak_backoff_seconds,
                subject=args.bundle_subject,
            )
            record_message_outcome(CONSUMER_SERVICE, outcome)

    await connection.drain()
    LOGGER.info("consumer stopped")
    return 0


def main(argv: list[str] | None = None) -> int:
    import os

    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    start_health_server(CONSUMER_SERVICE)
    return asyncio.run(run(args, os.environ))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
