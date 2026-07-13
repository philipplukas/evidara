"""Unit tests for the NATS→legal-search + platform-control event bridge (M0.2, #550)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from document_intelligence.jobs import projection_bridge_consumer as bridge
from document_intelligence.jobs.projection_bridge_consumer import (
    AuthForwardError,
    PermanentForwardError,
    forward_message,
    post_projection_event,
)

_EVENT = json.dumps(
    {
        "event_type": "document.processed",
        "event_id": "evt_processed_1",
        "payload": {"document_id": "doc_1", "provenance": {"run_id": "run_1"}},
    }
).encode("utf-8")

_WITHDRAWN_EVENT = json.dumps(
    {
        "event_type": "document.withdrawn",
        "event_id": "evt_withdrawn_1",
        "payload": {"document_id": "doc_1", "provenance": {"run_id": "run_1"}},
    }
).encode("utf-8")

_STATUS_EVENT = json.dumps(
    {
        "event_type": "document.processing_status.updated",
        "event_id": "evt_status_1",
        "payload": {"status": "processing", "provenance": {"run_id": "run_1"}},
    }
).encode("utf-8")

_LEGAL_SEARCH_URL = "http://ls:8080"
_PLATFORM_CONTROL_URL = "http://pc:8080"


def _bridge_args(*extra: str):  # noqa: ANN202
    """Parse bridge args with both peers wired — the deployed configuration."""
    return bridge._parse_args(
        [
            "--legal-search-api-url",
            _LEGAL_SEARCH_URL,
            "--platform-control-api-url",
            _PLATFORM_CONTROL_URL,
            *extra,
        ]
    )


class FakeMessage:
    def __init__(self, data: bytes, *, num_delivered: int = 1) -> None:
        self._data = data
        self._num_delivered = num_delivered
        self.acked = False
        self.terminated = False
        self.naks: list[float | None] = []

    @property
    def data(self) -> bytes:
        return self._data

    @property
    def num_delivered(self) -> int:
        return self._num_delivered

    async def ack(self) -> None:
        self.acked = True

    async def nak(self, delay: float | None = None) -> None:
        self.naks.append(delay)

    async def term(self) -> None:
        self.terminated = True


class _DlqRecorder:
    def __init__(self) -> None:
        self.published: list[bytes] = []

    async def __call__(self, data: bytes) -> None:
        self.published.append(data)


def _make_forward(*, error: Exception | None = None):
    calls: list[bytes] = []

    async def forward(data: bytes) -> None:
        calls.append(data)
        if error is not None:
            raise error

    return forward, calls


def _forward_message(message, *, forward, dlq, max_deliver=5):
    return asyncio.run(
        forward_message(
            message,
            forward=forward,
            dlq_publish=dlq,
            max_deliver=max_deliver,
            nak_backoff_seconds=2.0,
        )
    )


class ForwardMessageTests(unittest.TestCase):
    def test_success_acks(self) -> None:
        message = FakeMessage(_EVENT)
        forward, calls = _make_forward()
        dlq = _DlqRecorder()

        outcome = _forward_message(message, forward=forward, dlq=dlq)

        self.assertEqual(outcome, "forwarded")
        self.assertTrue(message.acked)
        self.assertFalse(message.terminated)
        self.assertEqual(message.naks, [])
        self.assertEqual(calls, [_EVENT])
        self.assertEqual(dlq.published, [])

    def test_permanent_error_terminates_without_dlq(self) -> None:
        message = FakeMessage(_EVENT)
        forward, _ = _make_forward(error=PermanentForwardError("422 invalid"))
        dlq = _DlqRecorder()

        outcome = _forward_message(message, forward=forward, dlq=dlq)

        self.assertEqual(outcome, "rejected_permanent")
        self.assertTrue(message.terminated)
        self.assertFalse(message.acked)
        self.assertEqual(message.naks, [])
        self.assertEqual(dlq.published, [])

    def test_transient_error_below_max_naks_for_retry(self) -> None:
        message = FakeMessage(_EVENT, num_delivered=1)
        forward, _ = _make_forward(error=RuntimeError("503"))
        dlq = _DlqRecorder()

        outcome = _forward_message(message, forward=forward, dlq=dlq, max_deliver=5)

        self.assertEqual(outcome, "transient_retry")
        self.assertEqual(message.naks, [2.0])
        self.assertFalse(message.terminated)
        self.assertFalse(message.acked)
        self.assertEqual(dlq.published, [])

    def test_auth_failure_naks_and_logs_loudly_at_error(self) -> None:
        """A failed callback must scream at ERROR, not pass silently (#550)."""
        message = FakeMessage(_STATUS_EVENT)
        forward, _ = _make_forward(error=AuthForwardError("POST http://pc/x rejected 401"))
        dlq = _DlqRecorder()

        with self.assertLogs(bridge.LOGGER, level="ERROR") as logs:
            outcome = _forward_message(message, forward=forward, dlq=dlq, max_deliver=5)

        self.assertEqual(outcome, "transient_retry")
        self.assertFalse(message.terminated)  # never silently dropped
        self.assertEqual(message.naks, [2.0])  # retried once the key is fixed
        self.assertEqual(dlq.published, [])
        logged = "\n".join(logs.output)
        self.assertIn("projection_forward_failed", logged)
        self.assertIn("AuthForwardError", logged)

    def test_transient_error_at_max_dead_letters(self) -> None:
        message = FakeMessage(_EVENT, num_delivered=5)
        forward, _ = _make_forward(error=RuntimeError("503"))
        dlq = _DlqRecorder()

        outcome = _forward_message(message, forward=forward, dlq=dlq, max_deliver=5)

        self.assertEqual(outcome, "dead_lettered")
        self.assertEqual(dlq.published, [_EVENT])
        self.assertTrue(message.terminated)
        self.assertEqual(message.naks, [])
        self.assertFalse(message.acked)


class _FakeHTTPResponse:
    def __init__(self, body: bytes = b"{}") -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="http://ls/v1/projections/events/document-processed",
        code=code,
        msg="err",
        hdrs=None,  # type: ignore[arg-type]
        fp=None,
    )


class PostProjectionEventTests(unittest.TestCase):
    def test_2xx_returns_and_sends_api_key(self) -> None:
        captured: dict[str, object] = {}

        def fake_urlopen(request, timeout=None):  # noqa: ANN001, ANN202
            captured["headers"] = request.headers
            captured["data"] = request.data
            return _FakeHTTPResponse()

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            post_projection_event("http://ls/x", _EVENT, api_key="secret")

        # urllib title-cases header keys.
        self.assertEqual(captured["headers"].get("X-api-key"), "secret")
        self.assertEqual(captured["data"], _EVENT)

    def test_no_api_key_omits_header(self) -> None:
        captured: dict[str, object] = {}

        def fake_urlopen(request, timeout=None):  # noqa: ANN001, ANN202
            captured["headers"] = request.headers
            return _FakeHTTPResponse()

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            post_projection_event("http://ls/x", _EVENT, api_key=None)

        self.assertNotIn("X-api-key", captured["headers"])

    def test_4xx_is_permanent(self) -> None:
        def fake_urlopen(request, timeout=None):  # noqa: ANN001, ANN202
            raise _http_error(422)

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            with self.assertRaises(PermanentForwardError):
                post_projection_event("http://ls/x", _EVENT, api_key=None)

    def test_429_is_transient(self) -> None:
        def fake_urlopen(request, timeout=None):  # noqa: ANN001, ANN202
            raise _http_error(429)

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            with self.assertRaises(RuntimeError) as ctx:
                post_projection_event("http://ls/x", _EVENT, api_key=None)
            self.assertNotIsInstance(ctx.exception, PermanentForwardError)

    def test_5xx_is_transient(self) -> None:
        def fake_urlopen(request, timeout=None):  # noqa: ANN001, ANN202
            raise _http_error(503)

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            with self.assertRaises(RuntimeError) as ctx:
                post_projection_event("http://ls/x", _EVENT, api_key=None)
            self.assertNotIsInstance(ctx.exception, PermanentForwardError)

    def test_401_is_auth_error_not_permanent_drop(self) -> None:
        """A missing/wrong X-API-Key must not be treated as a bad event (#550).

        Terminating on 401 would silently discard the callback forever; it is our
        config that is wrong, so it has to stay retryable.
        """

        def fake_urlopen(request, timeout=None):  # noqa: ANN001, ANN202
            raise _http_error(401)

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            with self.assertRaises(AuthForwardError) as ctx:
                post_projection_event("http://pc/x", _STATUS_EVENT, api_key=None)

        self.assertNotIsInstance(ctx.exception, PermanentForwardError)
        self.assertIsInstance(ctx.exception, RuntimeError)  # => transient path
        self.assertIn("NOT set", str(ctx.exception))

    def test_403_is_auth_error_not_permanent_drop(self) -> None:
        def fake_urlopen(request, timeout=None):  # noqa: ANN001, ANN202
            raise _http_error(403)

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            with self.assertRaises(AuthForwardError):
                post_projection_event("http://pc/x", _STATUS_EVENT, api_key="wrong")


class _LoopBreak(Exception):
    """Sentinel to end the otherwise-infinite consumer loop deterministically."""


class _RawMeta:
    def __init__(self, num_delivered: int = 1) -> None:
        self.num_delivered = num_delivered


class _RawNatsMessage:
    def __init__(self, data: bytes, *, num_delivered: int = 1) -> None:
        self.data = data
        self.metadata = _RawMeta(num_delivered)
        self.acked = False
        self.naks: list[float | None] = []
        self.terminated = False

    async def ack(self) -> None:
        self.acked = True

    async def nak(self, delay: float | None = None) -> None:
        self.naks.append(delay)

    async def term(self) -> None:
        self.terminated = True


class _IdleThenMessageSubscription:
    def __init__(self, message: _RawNatsMessage) -> None:
        self._message = message
        self.calls = 0

    async def fetch(self, batch: int, timeout: float | None = None) -> list[_RawNatsMessage]:
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError  # idle pull — nats-py 2.15 raises the builtin
        if self.calls == 2:
            return [self._message]
        raise _LoopBreak


class _FakeConnection:
    def __init__(self, jetstream: _RoutingJetStream) -> None:
        self._jetstream = jetstream
        self.drained = False

    def jetstream(self) -> _RoutingJetStream:
        return self._jetstream

    async def drain(self) -> None:
        self.drained = True


class BridgeRunLoopTests(unittest.TestCase):
    def test_idle_fetch_timeout_does_not_crash_loop_and_forwards(self) -> None:
        raw = _RawNatsMessage(_EVENT)
        subscription = _IdleThenMessageSubscription(raw)
        jetstream = _RoutingJetStream(
            {
                "evidara.document-processed": subscription,
                "evidara.document-withdrawn": _AlwaysIdleSubscription(),
                "evidara.document-processing-status-updated": _AlwaysIdleSubscription(),
            }
        )
        connection = _FakeConnection(jetstream)
        forwarded: list[bytes] = []

        async def _fake_connect(servers):  # noqa: ANN001, ANN202
            return connection

        def _fake_post(url, data, *, api_key, timeout=30.0):  # noqa: ANN001, ANN202
            forwarded.append(data)

        args = _bridge_args()

        with (
            mock.patch("nats.connect", _fake_connect),
            mock.patch.object(bridge, "post_projection_event", _fake_post),
        ):
            with self.assertRaises(_LoopBreak):
                asyncio.run(bridge.run(args))

        self.assertEqual(subscription.calls, 3)  # idle, message, sentinel
        self.assertTrue(raw.acked)
        # Fanned out to both peers.
        self.assertEqual(forwarded, [_EVENT, _EVENT])

    def test_missing_api_url_returns_error_code(self) -> None:
        args = _bridge_args()
        args.legal_search_api_url = None
        self.assertEqual(asyncio.run(bridge.run(args)), 2)

    def test_missing_platform_control_url_returns_error_code(self) -> None:
        """Refuse to start half-wired: a bridge without platform-control is the #550 bug."""
        args = _bridge_args()
        args.platform_control_api_url = None
        self.assertEqual(asyncio.run(bridge.run(args)), 2)


class _AlwaysIdleSubscription:
    async def fetch(self, batch: int, timeout: float | None = None) -> list[_RawNatsMessage]:
        raise TimeoutError  # idle pull — nothing pending on this subject


class _OnceSubscription:
    def __init__(self, message: _RawNatsMessage) -> None:
        self._message = message
        self.calls = 0

    async def fetch(self, batch: int, timeout: float | None = None) -> list[_RawNatsMessage]:
        self.calls += 1
        if self.calls == 1:
            return [self._message]
        raise _LoopBreak


class _RoutingJetStream:
    def __init__(self, subs_by_subject: dict[str, object]) -> None:
        self._subs = subs_by_subject
        self.published: list[tuple[str, bytes, dict | None]] = []

    async def pull_subscribe(self, subject, durable, stream, config):  # noqa: ANN001
        return self._subs[subject]

    async def publish(self, subject, payload, headers=None):  # noqa: ANN001
        self.published.append((subject, payload, headers))


def _run_bridge_with(
    subs: dict[str, object],
    *,
    args=None,  # noqa: ANN001
) -> tuple[list[tuple[str, bytes, str | None]], _RoutingJetStream]:
    """Drive run() once over the given per-subject subscriptions; capture the POSTs."""
    jetstream = _RoutingJetStream(subs)
    connection = _FakeConnection(jetstream)
    posted: list[tuple[str, bytes, str | None]] = []

    async def _fake_connect(servers):  # noqa: ANN001, ANN202
        return connection

    def _fake_post(url, data, *, api_key, timeout=30.0):  # noqa: ANN001, ANN202
        posted.append((url, data, api_key))

    with (
        mock.patch("nats.connect", _fake_connect),
        mock.patch.object(bridge, "post_projection_event", _fake_post),
    ):
        try:
            asyncio.run(bridge.run(args if args is not None else _bridge_args()))
        except _LoopBreak:
            pass

    return posted, jetstream


class RouteTests(unittest.TestCase):
    def test_parse_args_defaults_include_all_three_subjects(self) -> None:
        args = _bridge_args()
        self.assertEqual(args.processed_subject, "evidara.document-processed")
        self.assertEqual(args.withdrawn_subject, "evidara.document-withdrawn")
        self.assertEqual(
            args.status_subject,
            "evidara.document-processing-status-updated",
        )

    def test_withdrawal_event_fans_out_to_both_peers_and_acks(self) -> None:
        raw = _RawNatsMessage(_WITHDRAWN_EVENT)
        posted, _ = _run_bridge_with(
            {
                "evidara.document-processed": _AlwaysIdleSubscription(),
                "evidara.document-withdrawn": _OnceSubscription(raw),
                "evidara.document-processing-status-updated": _AlwaysIdleSubscription(),
            }
        )

        self.assertEqual(
            [(url, data) for url, data, _ in posted],
            [
                (f"{_LEGAL_SEARCH_URL}/v1/projections/events/document-withdrawn", _WITHDRAWN_EVENT),
                (f"{_PLATFORM_CONTROL_URL}/v1/di/events/document-withdrawn", _WITHDRAWN_EVENT),
            ],
        )
        self.assertTrue(raw.acked)

    def test_processed_event_fans_out_to_legal_search_and_platform_control(self) -> None:
        """Before #550 only legal-search got this — so document_lifecycle_events stayed 0."""
        raw = _RawNatsMessage(_EVENT)
        posted, _ = _run_bridge_with(
            {
                "evidara.document-processed": _OnceSubscription(raw),
                "evidara.document-withdrawn": _AlwaysIdleSubscription(),
                "evidara.document-processing-status-updated": _AlwaysIdleSubscription(),
            }
        )

        self.assertEqual(
            [(url, data) for url, data, _ in posted],
            [
                (f"{_LEGAL_SEARCH_URL}/v1/projections/events/document-processed", _EVENT),
                (f"{_PLATFORM_CONTROL_URL}/v1/di/events/document-processed", _EVENT),
            ],
        )
        self.assertTrue(raw.acked)

    def test_status_event_forwarded_to_platform_control_with_operator_key(self) -> None:
        """The subject that previously had no consumer at all (#550).

        Nothing consumed evidara.document-processing-status-updated, so every run's
        pipeline-health sat at `pending` forever. It must now reach platform-control —
        and only platform-control; legal-search has no use for status updates.
        """
        raw = _RawNatsMessage(_STATUS_EVENT)
        posted, _ = _run_bridge_with(
            {
                "evidara.document-processed": _AlwaysIdleSubscription(),
                "evidara.document-withdrawn": _AlwaysIdleSubscription(),
                "evidara.document-processing-status-updated": _OnceSubscription(raw),
            },
            args=_bridge_args("--platform-control-api-key", "operator-key"),
        )

        self.assertEqual(
            posted,
            [
                (
                    f"{_PLATFORM_CONTROL_URL}/v1/di/events/document-processing-status-updated",
                    _STATUS_EVENT,
                    "operator-key",
                )
            ],
        )
        self.assertTrue(raw.acked)


if __name__ == "__main__":
    unittest.main()
