"""Opt-in integration test: real NATS JetStream round-trip (ADR-0029).

Exercises the actual nats-py publish/consume path that the unit tests fake — stream
creation, ``Nats-Msg-Id`` dedup, and a real message acked through the consumer's
``_NatsMessage`` adapter + ``dispatch_message``.

Gated on ``EVIDARA_NATS_IT=1`` and the ``it`` extra (testcontainers + Docker), so it
skips cleanly everywhere else:

    cd document-intelligence
    EVIDARA_NATS_IT=1 uv run --extra it pytest tests/test_nats_integration.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    import nats
    from nats.errors import TimeoutError as NatsTimeoutError
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.waiting_utils import wait_for_logs

    _HAVE_DEPS = True
except Exception:  # pragma: no cover - optional integration deps
    _HAVE_DEPS = False

from document_intelligence.events.publisher import (
    NatsDocumentEventPublisher,
    NatsEventPublisherConfig,
)

_RUN_IT = os.environ.get("EVIDARA_NATS_IT") == "1"


class _Result:
    status_events = [{"event_type": "document.processing_status.updated", "event_id": "evt_status_it"}]
    document_processed_event = {"event_type": "document.processed", "event_id": "evt_processed_it"}


class _FakePipeline:
    def process_event(self, payload: dict) -> _Result:
        return _Result()


async def _noop_dlq(_data: bytes) -> None:
    return None


@unittest.skipUnless(_RUN_IT and _HAVE_DEPS, "set EVIDARA_NATS_IT=1 and install [it] extra (Docker required)")
class NatsJetStreamIntegrationTests(unittest.TestCase):
    def test_publish_dedup_and_real_ack_roundtrip(self) -> None:
        container = DockerContainer("nats:2.10-alpine").with_command("-js").with_exposed_ports(4222)
        container.start()
        try:
            wait_for_logs(container, "Server is ready", timeout=30)
            host = container.get_container_host_ip()
            port = container.get_exposed_port(4222)
            asyncio.run(self._roundtrip(f"nats://{host}:{port}"))
        finally:
            container.stop()

    async def _roundtrip(self, url: str) -> None:
        from document_intelligence.jobs.nats_consumer import _NatsMessage, dispatch_message

        connection = await nats.connect(url)
        jetstream = connection.jetstream()
        await jetstream.add_stream(
            name="EVIDARA_IT",
            subjects=["evidara.it.>"],
            duplicate_window=120,
        )

        # --- publisher dedup: same event_id published twice -> one stored message ---
        publisher = NatsDocumentEventPublisher(
            jetstream,
            NatsEventPublisherConfig(
                status_subject="evidara.it.status",
                processed_subject="evidara.it.processed",
            ),
        )
        processed = {"event_type": "document.processed", "event_id": "evt_dupe"}
        await publisher.publish_document_processed_event(processed)
        await publisher.publish_document_processed_event(processed)  # deduped

        proc_sub = await jetstream.pull_subscribe("evidara.it.processed", durable="it-proc", stream="EVIDARA_IT")
        proc_msgs = await proc_sub.fetch(5, timeout=2)
        self.assertEqual(len(proc_msgs), 1)
        self.assertEqual(json.loads(proc_msgs[0].data)["event_id"], "evt_dupe")
        await proc_msgs[0].ack()

        # --- real message acked through the consumer adapter + dispatch_message ---
        bundle = {
            "event_type": "artifact_bundle.available",
            "event_id": "evt_bundle_it",
            "payload": {"provenance": {"run_id": "run_it"}},
        }
        await jetstream.publish("evidara.it.bundle", json.dumps(bundle).encode("utf-8"))
        bundle_sub = await jetstream.pull_subscribe("evidara.it.bundle", durable="it-bundle", stream="EVIDARA_IT")
        msgs = await bundle_sub.fetch(1, timeout=2)
        outcome = await dispatch_message(
            _NatsMessage(msgs[0]),
            pipeline=_FakePipeline(),
            publisher=None,
            dlq_publish=_noop_dlq,
            max_deliver=5,
            nak_backoff_seconds=1.0,
        )
        self.assertEqual(outcome, "processed")

        # acked -> not redelivered
        redelivered: list[object] = []
        try:
            redelivered = await bundle_sub.fetch(1, timeout=1)
        except NatsTimeoutError:
            redelivered = []
        self.assertEqual(redelivered, [])

        await connection.drain()


if __name__ == "__main__":
    unittest.main()
