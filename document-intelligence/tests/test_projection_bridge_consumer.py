"""Unit tests for the NATS→legal-search projection bridge (M0.2)."""

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


class _FakeJetStream:
    def __init__(self, subscription: _IdleThenMessageSubscription) -> None:
        self._subscription = subscription
        self.published: list[tuple[str, bytes, dict | None]] = []

    async def pull_subscribe(self, subject, durable, stream, config):  # noqa: ANN001
        return self._subscription

    async def publish(self, subject, payload, headers=None):  # noqa: ANN001
        self.published.append((subject, payload, headers))


class _FakeConnection:
    def __init__(self, jetstream: _FakeJetStream) -> None:
        self._jetstream = jetstream
        self.drained = False

    def jetstream(self) -> _FakeJetStream:
        return self._jetstream

    async def drain(self) -> None:
        self.drained = True


class BridgeRunLoopTests(unittest.TestCase):
    def test_idle_fetch_timeout_does_not_crash_loop_and_forwards(self) -> None:
        raw = _RawNatsMessage(_EVENT)
        subscription = _IdleThenMessageSubscription(raw)
        connection = _FakeConnection(_FakeJetStream(subscription))
        forwarded: list[bytes] = []

        async def _fake_connect(servers):  # noqa: ANN001, ANN202
            return connection

        def _fake_post(url, data, *, api_key, timeout=30.0):  # noqa: ANN001, ANN202
            forwarded.append(data)

        args = bridge._parse_args(["--legal-search-api-url", "http://ls:8080"])

        with (
            mock.patch("nats.connect", _fake_connect),
            mock.patch.object(bridge, "post_projection_event", _fake_post),
        ):
            with self.assertRaises(_LoopBreak):
                asyncio.run(bridge.run(args))

        self.assertEqual(subscription.calls, 3)  # idle, message, sentinel
        self.assertTrue(raw.acked)
        self.assertEqual(forwarded, [_EVENT])

    def test_missing_api_url_returns_error_code(self) -> None:
        args = bridge._parse_args([])
        args.legal_search_api_url = None
        self.assertEqual(asyncio.run(bridge.run(args)), 2)


if __name__ == "__main__":
    unittest.main()
