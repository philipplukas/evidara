"""Structured event logging for platform-control."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

_ENVIRONMENT = os.environ.get("ENVIRONMENT", "unknown")
_SERVICE = "platform-control"


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    *,
    event_type: str | None = None,
    event_id: str | None = None,
    correlation_id: str | None = None,
    run_id: str | None = None,
    document_id: str | None = None,
    status: str | None = None,
    error_class: str | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
    duration_ms: float | None = None,
    **extra: Any,
) -> None:
    """Emit a structured JSON log entry with the shared event schema.

    All non-None keyword arguments are included in the output.  The
    ``event``, ``service``, and ``environment`` fields are always
    present.
    """
    fields: dict[str, Any] = {
        "event": event,
        "service": _SERVICE,
        "environment": _ENVIRONMENT,
    }

    for key, value in [
        ("event_type", event_type),
        ("event_id", event_id),
        ("correlation_id", correlation_id),
        ("run_id", run_id),
        ("document_id", document_id),
        ("status", status),
        ("error_class", error_class),
        ("error_type", error_type),
        ("error_message", error_message),
        ("duration_ms", duration_ms),
    ]:
        if value is not None:
            fields[key] = value

    fields.update(extra)
    logger.log(level, json.dumps(fields, default=str))
