"""The funnel counters platform-control contributes (ADR-0031, #553)."""

from __future__ import annotations

from prometheus_client import REGISTRY

from platform_control.observability import metrics


def _sample(name: str, **labels: str) -> float:
    value = REGISTRY.get_sample_value(name, labels or None)
    return 0.0 if value is None else value


def test_run_launched_counter_is_labelled_by_provider() -> None:
    before = _sample("platform_control_runs_launched_total", provider="firecrawl")

    metrics.record_run_launched("firecrawl")

    assert _sample("platform_control_runs_launched_total", provider="firecrawl") == before + 1


def test_artifact_capture_paths_are_counted_separately() -> None:
    # Two capture paths exist (synchronous providers and the async Firecrawl webhook);
    # a funnel that only counted one would under-report and look like a leak.
    inline_before = _sample("platform_control_artifacts_captured_total", path="inline")
    webhook_before = _sample("platform_control_artifacts_captured_total", path="webhook")

    metrics.record_artifact_captured("inline")
    metrics.record_artifact_captured("webhook")
    metrics.record_artifact_captured("webhook")

    assert _sample("platform_control_artifacts_captured_total", path="inline") == inline_before + 1
    assert (
        _sample("platform_control_artifacts_captured_total", path="webhook") == webhook_before + 2
    )


def test_bundle_event_counter_ignores_empty_batches() -> None:
    before = _sample("platform_control_bundle_events_published_total")

    metrics.record_bundle_event_published(0)
    assert _sample("platform_control_bundle_events_published_total") == before

    metrics.record_bundle_event_published(3)
    assert _sample("platform_control_bundle_events_published_total") == before + 3


def test_di_event_counter_is_labelled_by_event_type() -> None:
    before = _sample("platform_control_di_events_received_total", event_type="document.processed")

    metrics.record_di_event_received("document.processed")

    assert (
        _sample("platform_control_di_events_received_total", event_type="document.processed")
        == before + 1
    )


def test_render_latest_emits_prometheus_text_exposition() -> None:
    metrics.record_run_launched("firecrawl")

    body = metrics.render_latest().decode("utf-8")

    assert "# TYPE platform_control_runs_launched_total counter" in body
    assert 'platform_control_runs_launched_total{provider="firecrawl"}' in body
