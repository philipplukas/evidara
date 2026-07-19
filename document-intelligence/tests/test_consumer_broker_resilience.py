"""NATS disconnect handling for the long-lived consumers (#722).

These are the narrow unit tests around the decision logic. They are *not* the evidence
that the defect is fixed — a mocked client cannot prove reconnection behaviour, and the
whole of #722 was that the real client's default (60 attempts x 2s, then close) expired
during a broker bounce. The reproduction against a real broker is in the PR.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import urllib.error
import urllib.request

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nats import errors as nats_errors  # noqa: E402

from document_intelligence.jobs._consumer_common import (  # noqa: E402
    RECONNECT_FOREVER,
    BrokerConnectionLost,
    BrokerHealth,
    fetch_messages,
    start_health_server,
)


class _Subscription:
    def __init__(self, outcome: object) -> None:
        self._outcome = outcome
        self.calls = 0

    async def fetch(self, batch: int, timeout: float) -> list[object]:
        self.calls += 1
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return list(self._outcome)


class _Connection:
    def __init__(self, connected: bool = True) -> None:
        self.is_connected = connected


def _fetch(outcome: object, *, health: BrokerHealth, connected: bool = True):
    return asyncio.run(
        fetch_messages(
            _Subscription(outcome),
            10,
            timeout=0.01,
            connection=_Connection(connected),
            service="test-consumer",
            health=health,
        )
    )


def test_retry_forever_is_the_configured_policy_not_the_library_default() -> None:
    # nats-py's default is a *bounded* 60 x 2s, which is what expired during a broker
    # bounce and closed the connection. -1 is "retry forever" and must stay explicit.
    assert RECONNECT_FOREVER == -1


def test_idle_fetch_is_not_an_error() -> None:
    health = BrokerHealth()
    # Builtin TimeoutError: nats-py 2.15's fetch raises the builtin, and nats.errors
    # defines a *subclass* — catching only the subclass is what crash-looped #513.
    assert _fetch(TimeoutError(), health=health) == []
    assert _fetch(nats_errors.TimeoutError(), health=health) == []


def test_closed_connection_raises_so_the_consumer_can_exit_non_zero() -> None:
    health = BrokerHealth()
    health.mark_connected()
    with pytest.raises(BrokerConnectionLost):
        _fetch(nats_errors.ConnectionClosedError(), health=health)
    # A closed connection must also stop claiming readiness.
    assert health.connected is False


def test_mid_reconnect_error_keeps_the_loop_alive_but_marks_broker_unreachable() -> None:
    # This is the #722 path: before the fix any non-timeout broker error escaped the
    # fetch loop and killed the process. Now it degrades readiness and retries.
    health = BrokerHealth()
    health.mark_connected()
    assert _fetch(nats_errors.NoServersError(), health=health) == []
    assert health.connected is False
    assert "unreachable" in health.detail


def test_successful_fetch_restores_broker_health() -> None:
    health = BrokerHealth()
    health.mark_disconnected("was down")
    sentinel = object()
    assert _fetch([sentinel], health=health) == [sentinel]
    assert health.connected is True


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _get(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_readiness_reflects_broker_connectivity_while_liveness_stays_green(monkeypatch) -> None:
    # The counterweight to retry-forever: a consumer that is waiting rather than
    # working must be visibly not working, without being restarted for it (#722).
    health = BrokerHealth()
    port = _free_port()
    monkeypatch.setenv("PORT", str(port))
    start_health_server("document-intelligence-broker-test", broker_health=health)

    base = f"http://127.0.0.1:{port}"

    health.mark_disconnected("disconnected from broker; reconnecting")
    status, body = _get(f"{base}/ready")
    assert status == 503
    assert body["broker_connected"] is False
    # Liveness must NOT fail here — the process is healthy and correctly retrying.
    assert _get(f"{base}/health")[0] == 200

    health.mark_connected()
    status, body = _get(f"{base}/ready")
    assert status == 200
    assert body["broker_connected"] is True
