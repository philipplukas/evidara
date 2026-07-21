"""Structured event logging for document-intelligence consumers."""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any

_SERVICE = "di-consumer"

_UNSET_ENVIRONMENT = "unknown"


@lru_cache(maxsize=1)
def _environment() -> str:
    """Resolve the environment tag for document-intelligence log lines.

    This used to read an unprefixed ``ENVIRONMENT`` variable that was set nowhere in
    the repo, so every deployed log line was tagged ``"unknown"`` (#712). It now reads
    ``DI_ENVIRONMENT``, matching the ``DI_`` prefix every other document-intelligence
    setting already uses (``DI_S3_ENDPOINT_URL``, ``DI_GCP_PROJECT_ID``,
    ``DI_EVENT_PUBLISHER_BACKEND``), and `infra/hetzner/apps/configmap.yaml` sets it for
    every pod.

    Unlike platform-control — which derives this from a *required* ``Settings.environment``
    and so fails at startup when it is missing — document-intelligence has no settings
    model, and its entrypoints include one-shot CLI jobs and the test suite. Making a
    missing tag fatal would therefore break every local invocation for the sake of a
    log field that, as #712 notes, gates nothing. So the fallback stays, but it no
    longer fails *silently*: an unset value is reported once per process, which is what
    was actually missing when this went unnoticed in production.

    Resolved lazily and cached; tests use ``_environment.cache_clear()``.
    """
    value = (os.environ.get("DI_ENVIRONMENT") or "").strip()
    if value:
        return value

    logging.getLogger(__name__).warning(
        json.dumps(
            {
                "event": "environment_tag_unset",
                "service": _SERVICE,
                "environment": _UNSET_ENVIRONMENT,
                "error_message": (
                    "DI_ENVIRONMENT is not set; every log line from this process will be "
                    "tagged environment=unknown and cannot be filtered or routed by "
                    "environment. Set it in the deployment config (see #712)."
                ),
            }
        )
    )
    return _UNSET_ENVIRONMENT


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    *,
    event_type: str | None = None,
    event_id: str | None = None,
    correlation_id: str | None = None,
    run_id: str | None = None,
    message_id: str | None = None,
    delivery_attempt: str | None = None,
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
        ("message_id", message_id),
        ("delivery_attempt", delivery_attempt),
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
