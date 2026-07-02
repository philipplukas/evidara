"""Broker-agnostic helpers shared by the Pub/Sub and NATS runtime consumers."""

from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from document_intelligence.contracts.envelope import EnvelopeError

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
    """Start a minimal health HTTP server on $PORT (default 8080) in a daemon thread.

    Runs off the synchronous/async consume loop so it never blocks message handling.
    """

    class _HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                body = json.dumps({"status": "ok", "service": service}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_error(404)

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
