"""Unit tests for the NATS JetStream consumer dispatch semantics (ADR-0029 Slice 3)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from document_intelligence.events.publisher import (
    AsyncEventPublisher,
    NatsDocumentEventPublisher,
    NatsEventPublisherConfig,
)
from document_intelligence.jobs import nats_consumer
from document_intelligence.jobs.nats_consumer import dispatch_message

_VALID_EVENT = json.dumps(
    {
        "event_type": "artifact_bundle.available",
        "event_id": "evt_bundle_1",
        "payload": {"provenance": {"run_id": "run_1"}},
    }
).encode("utf-8")


class _Result:
    def __init__(self) -> None:
        self.status_events = [{"event_type": "document.processing_status.updated", "event_id": "evt_status_1"}]
        self.document_processed_event = {
            "event_type": "document.processed",
            "event_id": "evt_processed_1",
        }


class FakePipeline:
    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error
        self.calls = 0

    def process_event(self, payload: dict) -> _Result:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return _Result()


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


class FakePublisher:
    def __init__(self) -> None:
        self.status: list[dict] = []
        self.processed: list[dict] = []

    async def publish_status_event(self, event: dict) -> None:
        self.status.append(event)

    async def publish_document_processed_event(self, event: dict) -> None:
        self.processed.append(event)


class _DlqRecorder:
    def __init__(self) -> None:
        self.published: list[bytes] = []

    async def __call__(self, data: bytes) -> None:
        self.published.append(data)


def _dispatch(message, *, pipeline, publisher, dlq, max_deliver=5):
    return asyncio.run(
        dispatch_message(
            message,
            pipeline=pipeline,
            publisher=publisher,
            dlq_publish=dlq,
            max_deliver=max_deliver,
            nak_backoff_seconds=2.0,
        )
    )


class DispatchMessageTests(unittest.TestCase):
    def test_success_acks_and_publishes(self) -> None:
        message = FakeMessage(_VALID_EVENT)
        publisher = FakePublisher()
        dlq = _DlqRecorder()

        outcome = _dispatch(message, pipeline=FakePipeline(), publisher=publisher, dlq=dlq)

        self.assertEqual(outcome, "processed")
        self.assertTrue(message.acked)
        self.assertFalse(message.terminated)
        self.assertEqual(message.naks, [])
        self.assertEqual(len(publisher.status), 1)
        self.assertEqual(len(publisher.processed), 1)
        self.assertEqual(dlq.published, [])

    def test_dry_run_without_publisher_still_acks(self) -> None:
        message = FakeMessage(_VALID_EVENT)
        dlq = _DlqRecorder()

        outcome = _dispatch(message, pipeline=FakePipeline(), publisher=None, dlq=dlq)

        self.assertEqual(outcome, "processed")
        self.assertTrue(message.acked)

    def test_permanent_error_terminates_without_dlq(self) -> None:
        # KeyError is a PERMANENT_ERROR (content-driven, deterministic).
        message = FakeMessage(_VALID_EVENT)
        dlq = _DlqRecorder()

        outcome = _dispatch(
            message, pipeline=FakePipeline(error=KeyError("missing")), publisher=FakePublisher(), dlq=dlq
        )

        self.assertEqual(outcome, "rejected_permanent")
        self.assertTrue(message.terminated)
        self.assertFalse(message.acked)
        self.assertEqual(message.naks, [])
        self.assertEqual(dlq.published, [])

    def test_invalid_json_is_permanent(self) -> None:
        message = FakeMessage(b"not-json")
        pipeline = FakePipeline()
        dlq = _DlqRecorder()

        outcome = _dispatch(message, pipeline=pipeline, publisher=FakePublisher(), dlq=dlq)

        self.assertEqual(outcome, "rejected_permanent")
        self.assertTrue(message.terminated)
        self.assertEqual(pipeline.calls, 0)  # never reached the pipeline

    def test_transient_error_below_max_naks_for_retry(self) -> None:
        message = FakeMessage(_VALID_EVENT, num_delivered=1)
        dlq = _DlqRecorder()

        outcome = _dispatch(
            message,
            pipeline=FakePipeline(error=RuntimeError("boom")),
            publisher=FakePublisher(),
            dlq=dlq,
            max_deliver=5,
        )

        self.assertEqual(outcome, "transient_retry")
        self.assertEqual(message.naks, [2.0])
        self.assertFalse(message.terminated)
        self.assertFalse(message.acked)
        self.assertEqual(dlq.published, [])

    def test_transient_error_at_max_dead_letters(self) -> None:
        message = FakeMessage(_VALID_EVENT, num_delivered=5)
        dlq = _DlqRecorder()

        outcome = _dispatch(
            message,
            pipeline=FakePipeline(error=RuntimeError("boom")),
            publisher=FakePublisher(),
            dlq=dlq,
            max_deliver=5,
        )

        self.assertEqual(outcome, "dead_lettered")
        self.assertEqual(dlq.published, [_VALID_EVENT])
        self.assertTrue(message.terminated)
        self.assertEqual(message.naks, [])
        self.assertFalse(message.acked)


class FakeJetStream:
    def __init__(self) -> None:
        self.published: list[tuple[str, bytes, dict[str, str] | None]] = []

    async def publish(self, subject, payload, headers=None):
        self.published.append((subject, payload, headers))
        return None


class NatsDocumentEventPublisherTests(unittest.TestCase):
    def test_publishes_to_configured_subjects_with_dedup_header(self) -> None:
        jetstream = FakeJetStream()
        publisher = NatsDocumentEventPublisher(
            jetstream,
            NatsEventPublisherConfig(
                status_subject="evidara.document-processing-status-updated",
                processed_subject="evidara.document-processed",
            ),
        )

        # Conforms to the async publisher port the consumer depends on.
        self.assertIsInstance(publisher, AsyncEventPublisher)

        asyncio.run(
            publisher.publish_status_event({"event_type": "document.processing_status.updated", "event_id": "evt_s"})
        )
        asyncio.run(
            publisher.publish_document_processed_event({"event_type": "document.processed", "event_id": "evt_p"})
        )

        status_subject, _, status_headers = jetstream.published[0]
        processed_subject, _, processed_headers = jetstream.published[1]
        self.assertEqual(status_subject, "evidara.document-processing-status-updated")
        self.assertEqual(processed_subject, "evidara.document-processed")
        self.assertEqual(status_headers, {"Nats-Msg-Id": "evt_s"})
        self.assertEqual(processed_headers, {"Nats-Msg-Id": "evt_p"})


class _LoopBreak(Exception):
    """Sentinel used to end the otherwise-infinite consumer loop deterministically."""


class _RawMeta:
    def __init__(self, num_delivered: int = 1) -> None:
        self.num_delivered = num_delivered


class _RawNatsMessage:
    """Minimal stand-in for a nats.aio JetStream message (what _NatsMessage adapts)."""

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
    """fetch(): idle-timeout, then one message, then break out of the loop."""

    def __init__(self, message: _RawNatsMessage) -> None:
        self._message = message
        self.calls = 0

    async def fetch(self, batch: int, timeout: float | None = None) -> list[_RawNatsMessage]:
        self.calls += 1
        if self.calls == 1:
            # nats-py 2.15 raises the *builtin* TimeoutError on an idle pull.
            raise TimeoutError
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


class ConsumerRunLoopTests(unittest.TestCase):
    def test_idle_fetch_timeout_does_not_crash_loop(self) -> None:
        # Regression (di-consumer crash-loop): PullSubscription.fetch raises the
        # builtin TimeoutError on an idle queue. The loop must treat that as a
        # no-op and keep polling. Before the fix the loop caught only
        # nats.errors.TimeoutError — which cannot catch a bare builtin TimeoutError
        # (a subclass except never catches a parent instance) — so the idle
        # timeout escaped run() and crash-looped the consumer whenever no bundles
        # were pending (the empty-corpus steady state).
        raw = _RawNatsMessage(_VALID_EVENT)
        subscription = _IdleThenMessageSubscription(raw)
        connection = _FakeConnection(_FakeJetStream(subscription))
        pipeline = FakePipeline()

        async def _fake_connect(servers):  # noqa: ANN001, ANN202
            return connection

        args = nats_consumer._parse_args(["--dry-run-publish"])

        with (
            mock.patch.object(nats_consumer, "_build_pipeline", return_value=pipeline),
            mock.patch("nats.connect", _fake_connect),
        ):
            # The loop only exits via our sentinel; if the idle timeout were NOT
            # swallowed, asyncio.TimeoutError (not _LoopBreak) would surface here.
            with self.assertRaises(_LoopBreak):
                asyncio.run(nats_consumer.run(args, {}))

        # Survived the idle timeout (call 1), processed the later message (call 2),
        # then hit the sentinel (call 3) — proof the loop kept polling.
        self.assertEqual(subscription.calls, 3)
        self.assertEqual(pipeline.calls, 1)
        self.assertTrue(raw.acked)


if __name__ == "__main__":
    unittest.main()
