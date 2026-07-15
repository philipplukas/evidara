"""Prometheus counters for the platform-control end of the pipeline funnel (ADR-0032).

Module-level counters on the default registry, mirroring `event_logging.py`: the call
sites are already the places that emit a structured log, so instrumenting them is a
one-line addition rather than a new abstraction.

These are the first two stages of the funnel — "runs launched" and "artifacts captured".
Everything downstream (DI messages processed, documents indexed, searches with hits) is
only interpretable relative to them: 12 runs launched and 0 documents indexed is a leak;
0 runs launched and 0 documents indexed is a quiet Tuesday.
"""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

__all__ = [
    "CONTENT_TYPE_LATEST",
    "record_artifact_captured",
    "record_bundle_event_published",
    "record_di_event_received",
    "record_firecrawl_webhook_unmatched",
    "record_run_launched",
    "render_latest",
]

_RUNS_LAUNCHED = Counter(
    "platform_control_runs_launched_total",
    "Runs handed to a provider and moved to RUNNING (API, worker and Temporal paths).",
    ["provider"],
)

_ARTIFACTS_CAPTURED = Counter(
    "platform_control_artifacts_captured_total",
    "Raw artifacts persisted from a provider capture.",
    ["path"],  # "inline" (synchronous provider) | "webhook" (async Firecrawl crawl.page)
)

_BUNDLE_EVENTS_PUBLISHED = Counter(
    "platform_control_bundle_events_published_total",
    "artifact_bundle.available events handed to the event publisher.",
)

_DI_EVENTS_RECEIVED = Counter(
    "platform_control_di_events_received_total",
    "Status callbacks received from document-intelligence.",
    ["event_type"],
)

_FIRECRAWL_WEBHOOKS_UNMATCHED = Counter(
    "platform_control_firecrawl_webhooks_unmatched_total",
    "Firecrawl webhook deliveries that matched no provider job/run and were not applied.",
    # reason: "unknown_job_id" (no ProviderJob for the payload's crawl id — usually a
    # webhook that raced the dispatch commit, so the retry should succeed) |
    # "missing_job_id" (payload carried no crawl id) |
    # "orphaned_provider_job" (ProviderJob exists but its Run does not).
    ["event_type", "reason"],
)


def record_run_launched(provider: str) -> None:
    _RUNS_LAUNCHED.labels(provider=provider).inc()


def record_artifact_captured(path: str) -> None:
    _ARTIFACTS_CAPTURED.labels(path=path).inc()


def record_bundle_event_published(count: int = 1) -> None:
    if count > 0:
        _BUNDLE_EVENTS_PUBLISHED.inc(count)


def record_di_event_received(event_type: str) -> None:
    _DI_EVENTS_RECEIVED.labels(event_type=event_type).inc()


def record_firecrawl_webhook_unmatched(*, event_type: str, reason: str) -> None:
    """Count a Firecrawl delivery we could not apply.

    A non-zero rate that does not drain is the signal that crawl events are being
    redelivered forever against state that will never exist — the run is stuck.
    """
    _FIRECRAWL_WEBHOOKS_UNMATCHED.labels(event_type=event_type, reason=reason).inc()


def render_latest() -> bytes:
    """Serialize the default registry in the Prometheus text exposition format."""
    return generate_latest()
