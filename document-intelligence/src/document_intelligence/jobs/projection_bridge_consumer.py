"""Always-on NATS→legal-search projection bridge (M0.2).

The document-intelligence consumer publishes ``document.processed`` events to the
NATS ``evidara.document-processed`` subject, but nothing forwarded them into
legal-search — so processed documents never became searchable without a manual
``local_outbox_replay`` run. This consumer closes that gap: it subscribes to the
processed subject and POSTs each event to the legal-search projections HTTP
endpoint, mirroring the ack/nak/term/DLQ semantics of :mod:`nats_consumer`.

Delivery semantics (same as the bundle consumer):

- forward succeeds (2xx)      -> ``ack``
- permanent error (HTTP 4xx)  -> ``term`` (bad event; retrying is futile)
- transient error (5xx / net) -> ``nak`` with backoff, until ``max_deliver``
- exhausted transient          -> publish to the DLQ subject, then ``term``

The projection endpoint is idempotent (it dedups by event/revision and returns
202 for stale/duplicate), so at-least-once redelivery is safe.

:func:`forward_message` operates on the broker-agnostic ``IncomingMessage``
interface and an injected ``forward`` coroutine, so it is unit-testable without a
live broker or HTTP server.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable

from document_intelligence.jobs._consumer_common import (
    extract_event_context,
    start_health_server,
)
from document_intelligence.jobs.nats_consumer import IncomingMessage, _NatsMessage
from document_intelligence.observability.event_logging import log_event

LOGGER = logging.getLogger("document_intelligence.projection_bridge")

# HTTP 4xx that are the message's fault -> permanent (drop). 408/425/429 are
# retry-worthy despite being 4xx, so they fall through to the transient path.
_TRANSIENT_4XX = frozenset({408, 425, 429})


class PermanentForwardError(RuntimeError):
    """The projection endpoint rejected the event as invalid — do not retry."""


async def forward_message(
    message: IncomingMessage,
    *,
    forward: Callable[[bytes], Awaitable[None]],
    dlq_publish: Callable[[bytes], Awaitable[None]],
    max_deliver: int,
    nak_backoff_seconds: float,
    subject: str = "",
    logger: logging.Logger = LOGGER,
) -> str:
    """Forward one document.processed event and ack/nak/term it.

    Outcomes: ``forwarded`` | ``rejected_permanent`` | ``transient_retry`` | ``dead_lettered``.
    """
    ctx = extract_event_context(message.data)
    try:
        await forward(message.data)
        await message.ack()
        log_event(
            logger,
            logging.INFO,
            "projection_forwarded",
            event_type=ctx["event_type"],
            event_id=ctx["event_id"],
            correlation_id=ctx["correlation_id"],
            run_id=ctx["run_id"],
            num_delivered=message.num_delivered,
            subject=subject,
        )
        return "forwarded"

    except PermanentForwardError as exc:
        await message.term()
        log_event(
            logger,
            logging.WARNING,
            "projection_rejected_permanent",
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
            await dlq_publish(message.data)
            await message.term()
            log_event(
                logger,
                logging.ERROR,
                "projection_dead_lettered",
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

        await message.nak(delay=nak_backoff_seconds)
        log_event(
            logger,
            logging.ERROR,
            "projection_forward_failed",
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


def post_projection_event(
    url: str,
    data: bytes,
    *,
    api_key: str | None,
    timeout: float = 30.0,
) -> None:
    """POST a raw event payload to the legal-search projections endpoint.

    Raises :class:`PermanentForwardError` on a client (4xx) rejection and
    :class:`RuntimeError` on a transient (5xx / network) failure.
    """
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if api_key:
        # legal-search ApiKeyGuard enforces X-API-Key (not bearer); no-op when unset.
        headers["X-API-Key"] = api_key
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
            return
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if 400 <= exc.code < 500 and exc.code not in _TRANSIENT_4XX:
            raise PermanentForwardError(f"POST {url} rejected {exc.code}: {body}") from exc
        raise RuntimeError(f"POST {url} failed {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"POST {url} network error: {exc.reason}") from exc


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    import os

    parser = argparse.ArgumentParser(
        prog="document_intelligence_projection_bridge",
        description="Forward NATS document.processed events into legal-search projections.",
    )
    parser.add_argument("--servers", default=os.environ.get("NATS_SERVERS", "nats://localhost:4222"))
    parser.add_argument("--stream", default="EVIDARA")
    parser.add_argument("--durable-name", default="legal-search-projection-bridge")
    parser.add_argument("--processed-subject", default="evidara.document-processed")
    parser.add_argument("--dlq-subject", default="evidara.document-processed.dlq")
    parser.add_argument(
        "--legal-search-api-url",
        default=os.environ.get("LEGAL_SEARCH_API_URL") or os.environ.get("NEXT_PUBLIC_API_URL"),
        help="legal-search API base URL (projections endpoint is derived from it).",
    )
    parser.add_argument(
        "--legal-search-api-key",
        default=os.environ.get("LEGAL_SEARCH_API_KEY"),
        help="Optional X-API-Key for the legal-search projections endpoint.",
    )
    parser.add_argument("--max-messages", type=int, default=10)
    parser.add_argument("--fetch-timeout-seconds", type=float, default=5.0)
    parser.add_argument("--max-deliver", type=int, default=5)
    parser.add_argument("--nak-backoff-seconds", type=float, default=5.0)
    parser.add_argument("--ack-wait-seconds", type=float, default=60.0)
    return parser.parse_args(argv)


async def run(args: argparse.Namespace) -> int:
    import nats
    from nats.js.api import AckPolicy, ConsumerConfig

    if not args.legal_search_api_url:
        LOGGER.error("legal-search API URL is required (set LEGAL_SEARCH_API_URL)")
        return 2

    projection_url = f"{str(args.legal_search_api_url).rstrip('/')}/v1/projections/events/document-processed"
    api_key = args.legal_search_api_key

    async def forward(data: bytes) -> None:
        # urllib is blocking — run it off the event loop so fetch/ack keep flowing.
        await asyncio.to_thread(post_projection_event, projection_url, data, api_key=api_key)

    connection = await nats.connect(args.servers)
    jetstream = connection.jetstream()

    async def dlq_publish(data: bytes) -> None:
        await jetstream.publish(args.dlq_subject, data)

    consumer_config = ConsumerConfig(
        durable_name=args.durable_name,
        ack_policy=AckPolicy.EXPLICIT,
        ack_wait=args.ack_wait_seconds,
        max_deliver=args.max_deliver + 2,
        filter_subject=args.processed_subject,
    )
    subscription = await jetstream.pull_subscribe(
        args.processed_subject,
        durable=args.durable_name,
        stream=args.stream,
        config=consumer_config,
    )

    should_stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, should_stop.set)

    LOGGER.info(
        "starting projection bridge on %s (subject=%s -> %s)",
        args.stream,
        args.processed_subject,
        projection_url,
    )
    while not should_stop.is_set():
        try:
            messages = await subscription.fetch(args.max_messages, timeout=args.fetch_timeout_seconds)
        except TimeoutError:
            # Idle fetch is the normal steady state, not an error (see nats_consumer
            # for the builtin-vs-nats TimeoutError subtlety that crash-looped #513).
            continue
        for msg in messages:
            await forward_message(
                _NatsMessage(msg),
                forward=forward,
                dlq_publish=dlq_publish,
                max_deliver=args.max_deliver,
                nak_backoff_seconds=args.nak_backoff_seconds,
                subject=args.processed_subject,
            )

    await connection.drain()
    LOGGER.info("projection bridge stopped")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    start_health_server("document-intelligence-projection-bridge")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
