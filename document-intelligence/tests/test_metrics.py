"""DI consumer funnel counters and the /metrics branch of the health server (#553)."""

from __future__ import annotations

import socket
import urllib.error
import urllib.request

from prometheus_client import REGISTRY

from document_intelligence.jobs._consumer_common import start_health_server
from document_intelligence.observability import metrics


def _sample(name: str, **labels: str) -> float:
    value = REGISTRY.get_sample_value(name, labels or None)
    return 0.0 if value is None else value


def test_message_outcomes_are_counted_by_terminal_outcome() -> None:
    # These are the exact strings dispatch_message returns, so a dead-lettered message
    # shows up as dead-lettered rather than vanishing from the funnel.
    service = "document-intelligence-nats-consumer"
    processed_before = _sample("di_messages_total", service=service, outcome="processed")
    dlq_before = _sample("di_messages_total", service=service, outcome="dead_lettered")

    metrics.record_message_outcome(service, "processed")
    metrics.record_message_outcome(service, "processed")
    metrics.record_message_outcome(service, "dead_lettered")

    assert _sample("di_messages_total", service=service, outcome="processed") == processed_before + 2
    assert _sample("di_messages_total", service=service, outcome="dead_lettered") == dlq_before + 1


def test_projection_forwards_are_counted_by_outcome() -> None:
    before = _sample("di_projection_forwards_total", outcome="forwarded")

    metrics.record_projection_outcome("forwarded")

    assert _sample("di_projection_forwards_total", outcome="forwarded") == before + 1


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def test_health_server_serves_both_health_and_metrics(monkeypatch) -> None:
    # One server, two endpoints: /health answers "the process is alive" (it always did,
    # even while the pipeline was dead) and /metrics answers "work is flowing".
    port = _free_port()
    monkeypatch.setenv("PORT", str(port))
    start_health_server("document-intelligence-test")

    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as response:
        assert response.status == 200
        assert b'"status": "ok"' in response.read()

    metrics.record_message_outcome("document-intelligence-test", "processed")
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=5) as response:
        assert response.status == 200
        body = response.read().decode("utf-8")
    assert "# TYPE di_messages_total counter" in body
    # prometheus_client renders labels alphabetically, not in declaration order.
    assert 'di_messages_total{outcome="processed",service="document-intelligence-test"}' in body

    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/nope", timeout=5)
    except urllib.error.HTTPError as error:
        assert error.code == 404
    else:  # pragma: no cover - defensive
        raise AssertionError("unknown paths must still 404")
