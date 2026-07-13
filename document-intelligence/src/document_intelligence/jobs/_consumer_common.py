"""Broker-agnostic helpers shared by the Pub/Sub and NATS runtime consumers."""

from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from document_intelligence.contracts.envelope import EnvelopeError
from document_intelligence.observability.metrics import CONTENT_TYPE_LATEST, render_latest

LOGGER = logging.getLogger("document_intelligence.runtime_consumer")

# Permanent failures are deterministic and message-content-driven: retrying the
# identical payload produces the same error, so they are dropped, never retried/DLQ'd.
PERMANENT_ERRORS = (EnvelopeError, json.JSONDecodeError, KeyError)


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


def start_health_server(service: str) -> None:
    """Start the health + metrics HTTP server on $PORT (default 8080) in a daemon thread.

    Serves ``GET /health`` (liveness — "the process is alive") and ``GET /metrics``
    (Prometheus — "work is actually flowing"). The consumers ran green on the former
    for weeks while doing nothing; the latter is the point of ADR-0031.

    Runs off the synchronous/async consume loop so it never blocks message handling.
    ``prometheus_client`` counters are thread-safe, so serialising them from this
    thread while the event loop increments them is safe.
    """

    class _HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                body = json.dumps({"status": "ok", "service": service}).encode()
                self._respond(200, "application/json", body)
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
