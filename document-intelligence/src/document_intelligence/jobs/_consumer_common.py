"""Broker-agnostic helpers shared by the Pub/Sub and NATS runtime consumers."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from document_intelligence.contracts.envelope import EnvelopeError
from document_intelligence.observability.metrics import CONTENT_TYPE_LATEST, render_latest

LOGGER = logging.getLogger("document_intelligence.runtime_consumer")

# Permanent failures are deterministic and message-content-driven: retrying the
# identical payload produces the same error, so they are dropped, never retried/DLQ'd.
PERMANENT_ERRORS = (EnvelopeError, json.JSONDecodeError, KeyError)

# Reconnect policy for the long-lived consumers (#722).
#
# nats-py's *default* is not "no reconnect" — it is a bounded one: 60 attempts at 2s,
# i.e. ~2 minutes. Neither consumer ever configured it, so both inherited that budget,
# and any broker outage longer than two minutes (a NATS upgrade, a node drain) expired
# it. The client then closed the connection and `subscription.fetch()` raised
# `ConnectionClosedError`, which escaped the fetch loop and killed the process.
#
# Retry forever instead. A consumer has nothing useful to do without the broker, and
# exiting is strictly worse than waiting: a restart re-runs pipeline construction and
# CrashLoopBackOff then adds exponential delay at exactly the moment the broker returns.
# The cost of retry-forever is that "waiting" and "working" look identical from the
# outside — which is the #722 misdiagnosis in a new costume. That is what
# `BROKER_HEALTH` and the `/ready` endpoint below are for: liveness stays green (the
# process is healthy and correctly retrying) while readiness goes red the moment the
# broker is gone, so a disconnected consumer is *visibly* not working (ADR-0032).
RECONNECT_FOREVER = -1
RECONNECT_TIME_WAIT_SECONDS = 2.0
CONNECT_TIMEOUT_SECONDS = 5.0


class BrokerHealth:
    """Thread-safe broker connectivity flag shared by the event loop and health server.

    Written from nats-py's connection callbacks on the event loop, read from the
    health server's thread, so every access takes the lock.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._connected = False
        self._detail = "not connected yet"

    def mark_connected(self, detail: str = "connected") -> None:
        with self._lock:
            self._connected = True
            self._detail = detail

    def mark_disconnected(self, detail: str) -> None:
        with self._lock:
            self._connected = False
            self._detail = detail

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    @property
    def detail(self) -> str:
        with self._lock:
            return self._detail


BROKER_HEALTH = BrokerHealth()


class BrokerConnectionLost(RuntimeError):
    """The NATS connection closed for good — the consumer must exit non-zero.

    With :data:`RECONNECT_FOREVER` the reconnect budget never expires on its own, so
    reaching this means something unrecoverable (an explicit close, an auth rejection,
    a protocol error). Dying quietly inside a running pod is what made #722 invisible;
    exiting non-zero hands the problem to the k8s restart policy (``Always``, the
    default, and unset in ``infra/hetzner/apps/document-intelligence.yaml``).
    """


async def connect_nats(servers: str, *, service: str, health: BrokerHealth = BROKER_HEALTH) -> Any:
    """Open a NATS connection with an explicit retry-forever reconnect policy (#722).

    The disconnect/reconnect/close callbacks are the point: they keep ``health`` — and
    therefore ``/ready`` — honest about whether this consumer can actually reach the
    broker, and they log the transition so an outage is legible in the pod logs.
    """
    import nats

    async def disconnected_cb() -> None:
        health.mark_disconnected("disconnected from broker; reconnecting")
        LOGGER.warning("%s: NATS disconnected — reconnecting (retry forever)", service)

    async def reconnected_cb() -> None:
        health.mark_connected("reconnected to broker")
        LOGGER.info("%s: NATS reconnected", service)

    async def closed_cb() -> None:
        health.mark_disconnected("connection closed")
        LOGGER.error("%s: NATS connection closed", service)

    async def error_cb(exc: Exception) -> None:
        LOGGER.warning("%s: NATS error: %s: %s", service, type(exc).__name__, exc)

    connection = await nats.connect(
        servers,
        max_reconnect_attempts=RECONNECT_FOREVER,
        reconnect_time_wait=RECONNECT_TIME_WAIT_SECONDS,
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
        disconnected_cb=disconnected_cb,
        reconnected_cb=reconnected_cb,
        closed_cb=closed_cb,
        error_cb=error_cb,
    )
    health.mark_connected()
    LOGGER.info("%s: connected to NATS at %s (reconnect: forever)", service, servers)
    return connection


async def fetch_messages(
    subscription: Any,
    batch: int,
    *,
    timeout: float,
    connection: Any,
    service: str,
    health: BrokerHealth = BROKER_HEALTH,
) -> list[Any]:
    """Fetch a batch, treating an idle or mid-reconnect broker as "no messages".

    Three outcomes have to stay distinguishable, and conflating them is what #722 was:

    - **timeout** — no pending messages within the window. The normal steady state.
      (nats-py 2.15's ``fetch`` raises the *builtin* ``TimeoutError``; ``nats.errors``
      defines a *subclass*, and a subclass ``except`` never catches a parent instance,
      which is what crash-looped #513. Catching the builtin covers both.)
    - **connection closed** — unrecoverable under retry-forever. Raise
      :class:`BrokerConnectionLost` so the consumer exits non-zero and k8s restarts it.
    - **any other broker error** — almost always the reconnect window. Mark the broker
      unreachable so ``/ready`` goes red, then return empty so the caller loops. The
      sleep keeps a persistent error from becoming a hot loop.
    """
    from nats import errors as nats_errors

    try:
        messages = await subscription.fetch(batch, timeout=timeout)
    except nats_errors.ConnectionClosedError as exc:
        health.mark_disconnected("connection closed")
        raise BrokerConnectionLost(f"{service}: NATS connection closed and cannot be recovered") from exc
    except TimeoutError:
        return []
    except nats_errors.Error as exc:
        health.mark_disconnected(f"broker unreachable: {type(exc).__name__}")
        LOGGER.warning(
            "%s: fetch failed while broker is unreachable (%s: %s) — retrying",
            service,
            type(exc).__name__,
            exc,
        )
        await asyncio.sleep(RECONNECT_TIME_WAIT_SECONDS)
        return []

    if connection.is_connected:
        health.mark_connected()
    return messages


def extract_event_context(data: bytes) -> dict[str, str | None]:
    """Best-effort extraction of event context fields for structured logging."""
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


def start_health_server(
    service: str,
    *,
    broker_health: BrokerHealth | None = None,
) -> None:
    """Start the health + metrics HTTP server on $PORT (default 8080) in a daemon thread.

    Serves three endpoints, and the split between the first two is load-bearing (#722):

    - ``GET /health`` — **liveness**: "the process is alive". Stays 200 during a broker
      outage on purpose. The consumer is healthy and correctly retrying; restarting it
      would only add CrashLoopBackOff delay to an outage it cannot fix.
    - ``GET /ready`` — **readiness**: "this consumer can reach the broker". Returns 503
      while disconnected. Retry-forever without this would trade a loudly dead consumer
      for a quietly idle one — the same lie #722 is about, one layer over.
    - ``GET /metrics`` — Prometheus: "work is actually flowing" (ADR-0032).

    Passing ``broker_health=None`` (the Pub/Sub consumers, which have no NATS
    connection) makes ``/ready`` mirror ``/health``.

    Runs off the synchronous/async consume loop so it never blocks message handling.
    ``prometheus_client`` counters are thread-safe, so serialising them from this
    thread while the event loop increments them is safe.
    """

    class _HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                body = json.dumps({"status": "ok", "service": service}).encode()
                self._respond(200, "application/json", body)
            elif self.path == "/ready":
                if broker_health is None:
                    payload = {"status": "ready", "service": service}
                    self._respond(200, "application/json", json.dumps(payload).encode())
                    return
                connected = broker_health.connected
                payload = {
                    "status": "ready" if connected else "not_ready",
                    "service": service,
                    "broker_connected": connected,
                    "detail": broker_health.detail,
                }
                self._respond(200 if connected else 503, "application/json", json.dumps(payload).encode())
            elif self.path == "/metrics":
                self._respond(200, CONTENT_TYPE_LATEST, render_latest())
            else:
                self.send_error(404)

        def _respond(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            """Silence default stderr logging to avoid noise."""

    port = int(os.environ.get("PORT", "8080"))
    try:
        server = HTTPServer(("", port), _HealthHandler)
    except OSError as exc:
        LOGGER.error("Failed to bind health server to port %d: %s", port, exc)
        raise
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    LOGGER.info("Health server listening on port %d", port)
