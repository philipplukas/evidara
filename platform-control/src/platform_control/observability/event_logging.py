"""Structured event logging for platform-control."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

_SERVICE = "platform-control"


@lru_cache(maxsize=1)
def _environment() -> str:
    """Resolve the environment tag from the one setting that already names it.

    This used to read a *separate*, unprefixed ``ENVIRONMENT`` variable that was set
    nowhere in the repo, so every deployed log line was tagged ``"unknown"`` (#712).
    Two variables meaning the same thing is what let them drift apart, so the fix is
    not to also set the second one — it is to delete it. ``Settings.environment``
    (``PLATFORM_CONTROL_ENVIRONMENT``) deliberately has no default since #683, so a
    deployment that fails to name its environment now fails loudly at startup rather
    than mislabelling its own audit trail.

    Resolved lazily and cached: importing this module must not require settings, and
    the value cannot change within a process. Tests use ``_environment.cache_clear()``.
    """
    from platform_control.config import get_settings

    return get_settings().environment


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
        "environment": _environment(),
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
