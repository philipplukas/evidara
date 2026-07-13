"""Always-on NATS→legal-search + platform-control event bridge (M0.2, issues #522/#550).

The document-intelligence consumer publishes its outbound events to NATS
(``evidara.document-processed``, ``evidara.document-withdrawn``,
``evidara.document-processing-status-updated``) but never calls any HTTP peer
itself. This bridge is the only process that turns those subjects into HTTP
calls, and it forwards each one to *every* consumer that needs it:

- ``evidara.document-processed``
    -> legal-search   ``POST /v1/projections/events/document-processed``
    -> platform-control ``POST /v1/di/events/document-processed``
- ``evidara.document-withdrawn``
    -> legal-search   ``POST /v1/projections/events/document-withdrawn``
    -> platform-control ``POST /v1/di/events/document-withdrawn``
- ``evidara.document-processing-status-updated``
    -> platform-control ``POST /v1/di/events/document-processing-status-updated``

Before #550 only the legal-search routes existed: the status subject had **no
consumer at all** and nothing ever reached platform-control, so every run's
``/v1/runs/{id}/pipeline-health`` sat at ``pending`` for document_intelligence /
projection / search even when the document processed fine and was searchable.
platform-control's ``PLATFORM_CONTROL_API_URL`` being present in the DI
consumer's environment was a red herring — it comes from the shared
``evidara-config`` ConfigMap and no DI code ever read it.

Delivery semantics (same as the bundle consumer):

- every target succeeds (2xx)  -> ``ack``
- permanent error (HTTP 4xx)   -> ``term`` (bad event; retrying is futile)
- transient error (5xx / net)  -> ``nak`` with backoff, until ``max_deliver``
- auth error (401/403)         -> transient: a missing/wrong API key is an operator
  misconfiguration, not a bad event. Terminating it would silently discard the
  event forever; instead it is logged at ERROR and retried, so the event still
  lands once the key is fixed.
- exhausted transient          -> publish to the DLQ subject, then ``term``

All target endpoints are idempotent (they dedup by event id / revision and return
202 for stale or duplicate deliveries), so at-least-once redelivery — including a
re-POST to a target that already succeeded before a *later* target in the same
fan-out failed — is safe.

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
from dataclasses import dataclass

from document_intelligence.jobs._consumer_common import (
    extract_event_context,
    start_health_server,
)
from document_intelligence.jobs.nats_consumer import IncomingMessage, _NatsMessage
from document_intelligence.observability.event_logging import log_event
from document_intelligence.observability.metrics import record_projection_outcome

LOGGER = logging.getLogger("document_intelligence.projection_bridge")

# HTTP 4xx that are the message's fault -> permanent (drop). 408/425/429 are
# retry-worthy despite being 4xx, so they fall through to the transient path.
_TRANSIENT_4XX = frozenset({408, 425, 429})

# 401/403 mean *we* are misconfigured (missing or wrong X-API-Key), not that the
# event is bad. Treated as transient so the event is retried/DLQ'd and logged at
# ERROR rather than silently terminated (#550).
_AUTH_STATUS = frozenset({401, 403})


class PermanentForwardError(RuntimeError):
    """The projection endpoint rejected the event as invalid — do not retry."""


class AuthForwardError(RuntimeError):
    """The endpoint rejected our credentials (401/403) — operator must fix the API key.

    A plain :class:`RuntimeError` subclass so it takes the transient (nak → retry →
    DLQ) path and is logged at ERROR; it exists as its own type only so the failure
    is unmistakable in ``error_type`` on the ``projection_forward_failed`` log line.
    """


@dataclass(frozen=True)
class ForwardTarget:
    """One HTTP endpoint an event is forwarded to."""

    url: str
    api_key: str | None


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
    """POST a raw event payload to a legal-search or platform-control endpoint.

    Raises :class:`AuthForwardError` on 401/403 (retryable — our key is wrong),
    :class:`PermanentForwardError` on any other client (4xx) rejection, and
    :class:`RuntimeError` on a transient (5xx / network) failure.
    """
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if api_key:
        # Both peers enforce X-API-Key (not bearer): legal-search's ApiKeyGuard and
        # platform-control's require_control_plane_service. No-op when unset.
        headers["X-API-Key"] = api_key
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
            return
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code in _AUTH_STATUS:
            # Config error, not a bad event — do NOT term/drop it (#550).
            raise AuthForwardError(
                f"POST {url} rejected {exc.code}: missing or invalid X-API-Key "
                f"(api_key {'set' if api_key else 'NOT set'}): {body}"
            ) from exc
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
    # Durable for the processed subject. Kept as the original name so an in-place
    # upgrade reuses the existing JetStream consumer rather than orphaning it.
    parser.add_argument("--durable-name", default="legal-search-projection-bridge")
    parser.add_argument("--withdrawn-durable-name", default="legal-search-projection-withdrawal")
    parser.add_argument("--status-durable-name", default="platform-control-processing-status")
    parser.add_argument("--processed-subject", default="evidara.document-processed")
    parser.add_argument("--withdrawn-subject", default="evidara.document-withdrawn")
    parser.add_argument("--status-subject", default="evidara.document-processing-status-updated")
    parser.add_argument("--dlq-subject", default="evidara.document-processed.dlq")
    parser.add_argument("--withdrawn-dlq-subject", default="evidara.document-withdrawn.dlq")
    parser.add_argument(
        "--status-dlq-subject",
        default="evidara.document-processing-status-updated.dlq",
    )
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
    parser.add_argument(
        "--platform-control-api-url",
        default=os.environ.get("PLATFORM_CONTROL_API_URL"),
        help="platform-control API base URL (the /v1/di/events endpoints are derived from it).",
    )
    parser.add_argument(
        "--platform-control-api-key",
        default=(os.environ.get("PLATFORM_CONTROL_OPERATOR_API_KEY") or os.environ.get("PLATFORM_CONTROL_API_KEY")),
        help=(
            "X-API-Key for platform-control's /v1/di/events endpoints. Required whenever "
            "platform-control has auth enabled; a missing key surfaces as a loud 401 retry."
        ),
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
    if not args.platform_control_api_url:
        # Without this the run-detail UI and the canary are blind for every run (#550) —
        # refuse to start half-wired rather than drop the callbacks on the floor.
        LOGGER.error("platform-control API URL is required (set PLATFORM_CONTROL_API_URL)")
        return 2
    if not args.platform_control_api_key:
        # Only a heads-up: an unauthenticated dev platform-control (docker-compose.local)
        # is legitimate, so this is not ERROR — crying wolf there would devalue the ERROR
        # that a real 401 raises per callback. In a deployed environment this is the #550
        # misconfiguration, and it will surface loudly on the first forward.
        LOGGER.warning(
            "no platform-control API key configured (set PLATFORM_CONTROL_OPERATOR_API_KEY); "
            "DI event callbacks will 401 unless platform-control has auth disabled"
        )

    legal_search_base = str(args.legal_search_api_url).rstrip("/")
    platform_control_base = str(args.platform_control_api_url).rstrip("/")

    def legal_search(path: str) -> ForwardTarget:
        return ForwardTarget(f"{legal_search_base}{path}", args.legal_search_api_key)

    def platform_control(path: str) -> ForwardTarget:
        return ForwardTarget(f"{platform_control_base}{path}", args.platform_control_api_key)

    connection = await nats.connect(args.servers)
    jetstream = connection.jetstream()

    def make_forward(*targets: ForwardTarget) -> Callable[[bytes], Awaitable[None]]:
        async def forward(data: bytes) -> None:
            # Sequential fan-out: the first failing target raises, so the message is
            # nak'd and every target is re-POSTed on redelivery. Safe because all of
            # them are idempotent (dedup by event id / revision -> 202).
            for target in targets:
                # urllib is blocking — run it off the event loop so fetch/ack keep flowing.
                await asyncio.to_thread(
                    post_projection_event,
                    target.url,
                    data,
                    api_key=target.api_key,
                )

        return forward

    def make_dlq(dlq_subject: str) -> Callable[[bytes], Awaitable[None]]:
        async def dlq_publish(data: bytes) -> None:
            await jetstream.publish(dlq_subject, data)

        return dlq_publish

    async def subscribe(subject: str, durable: str):  # noqa: ANN202
        consumer_config = ConsumerConfig(
            durable_name=durable,
            ack_policy=AckPolicy.EXPLICIT,
            ack_wait=args.ack_wait_seconds,
            max_deliver=args.max_deliver + 2,
            filter_subject=subject,
        )
        return await jetstream.pull_subscribe(
            subject,
            durable=durable,
            stream=args.stream,
            config=consumer_config,
        )

    # One process, one subscription per subject, fanned out to every endpoint that needs
    # the event. legal-search makes it searchable; platform-control records it so
    # /v1/runs/{id}/pipeline-health can advance past `pending` (#550). All endpoints are
    # idempotent, so at-least-once redelivery on any route is safe.
    routes = [
        (
            await subscribe(args.processed_subject, args.durable_name),
            args.processed_subject,
            make_forward(
                legal_search("/v1/projections/events/document-processed"),
                platform_control("/v1/di/events/document-processed"),
            ),
            make_dlq(args.dlq_subject),
        ),
        (
            await subscribe(args.withdrawn_subject, args.withdrawn_durable_name),
            args.withdrawn_subject,
            make_forward(
                legal_search("/v1/projections/events/document-withdrawn"),
                platform_control("/v1/di/events/document-withdrawn"),
            ),
            make_dlq(args.withdrawn_dlq_subject),
        ),
        (
            # Status updates are control-plane only — legal-search has no use for them.
            await subscribe(args.status_subject, args.status_durable_name),
            args.status_subject,
            make_forward(
                platform_control("/v1/di/events/document-processing-status-updated"),
            ),
            make_dlq(args.status_dlq_subject),
        ),
    ]

    should_stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, should_stop.set)

    LOGGER.info(
        "starting projection bridge on %s (subjects=%s, %s, %s -> legal-search %s, platform-control %s)",
        args.stream,
        args.processed_subject,
        args.withdrawn_subject,
        args.status_subject,
        legal_search_base,
        platform_control_base,
    )
    while not should_stop.is_set():
        for subscription, subject, forward, dlq_publish in routes:
            try:
                messages = await subscription.fetch(args.max_messages, timeout=args.fetch_timeout_seconds)
            except TimeoutError:
                # Idle fetch is the normal steady state, not an error (see nats_consumer
                # for the builtin-vs-nats TimeoutError subtlety that crash-looped #513).
                continue
            for msg in messages:
                outcome = await forward_message(
                    _NatsMessage(msg),
                    forward=forward,
                    dlq_publish=dlq_publish,
                    max_deliver=args.max_deliver,
                    nak_backoff_seconds=args.nak_backoff_seconds,
                    subject=subject,
                )
                record_projection_outcome(outcome)

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
