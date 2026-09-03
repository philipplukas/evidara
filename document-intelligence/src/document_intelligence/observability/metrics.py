"""Prometheus counters for the document-intelligence consumers (ADR-0032).

Two middle stages of the pipeline funnel:

* ``di_messages_total{outcome="processed"}`` — artifact bundles the DI consumer turned
  into a ``document.processed`` event.
* ``di_projection_forwards_total{outcome="forwarded"}`` — those events the projection
  bridge actually delivered to legal-search.

The outcome labels are exactly the strings ``dispatch_message`` and ``forward_message``
already return, so the counters cannot drift from the code paths they describe: a
message that is dead-lettered is counted as dead-lettered, not silently dropped from
the denominator.

Counters live on the default registry and are scraped over the health server the
consumers already run (see ``jobs/_consumer_common.py``) — no second HTTP listener.
"""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

__all__ = [
    "CONTENT_TYPE_LATEST",
    "record_message_outcome",
    "record_projection_outcome",
    "record_quarantine",
    "render_latest",
]

_MESSAGES = Counter(
    "di_messages_total",
    "Artifact-bundle messages handled by a DI consumer, by terminal outcome.",
    ["service", "outcome"],
)

_PROJECTION_FORWARDS = Counter(
    "di_projection_forwards_total",
    "document.processed events the projection bridge forwarded to legal-search, by terminal outcome.",
    ["outcome"],
)


_QUARANTINED = Counter(
    "di_quarantined_documents_total",
    "Manifestations withheld from the canonical corpus, by ADR-0047 reason slug.",
    ["reason"],
)


def record_quarantine(reason: str) -> None:
    """Count one quarantined manifestation (ADR-0047 §6).

    The per-reason breakdown is the point, not the total: the slug decides which of the
    ADR's two exits the cohort takes — fix our logic, or implement the missing class. A
    bare count would say the corpus is losing documents without saying what to build.
    """
    _QUARANTINED.labels(reason=reason).inc()


def record_message_outcome(service: str, outcome: str) -> None:
    """Count one consumed message. `outcome` is dispatch_message's return value."""
    _MESSAGES.labels(service=service, outcome=outcome).inc()


def record_projection_outcome(outcome: str) -> None:
    """Count one bridged event. `outcome` is forward_message's return value."""
    _PROJECTION_FORWARDS.labels(outcome=outcome).inc()


def render_latest() -> bytes:
    """Serialize the default registry in the Prometheus text exposition format."""
    return generate_latest()
