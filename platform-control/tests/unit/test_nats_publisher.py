from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from typing import Any

import pytest

from platform_control.events.publisher import NatsRawArtifactPublisher
from platform_control.models.raw_artifact import RawArtifact


class FakeJetStream:
    """Minimal stand-in for a nats JetStream context."""

    def __init__(self) -> None:
        self.published: list[tuple[str, bytes, dict[str, str] | None]] = []
        self.timeouts: list[float | None] = []

    async def publish(
        self,
        subject: str,
        payload: bytes,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any:
        self.published.append((subject, payload, headers))
        self.timeouts.append(timeout)
        return None


def _publisher(jetstream: FakeJetStream) -> NatsRawArtifactPublisher:
    return NatsRawArtifactPublisher(
        servers="nats://test:4222",
        raw_artifact_subject="evidara.raw-artifact-available",
        artifact_bundle_subject="evidara.artifact-bundle-available",
        jetstream=jetstream,
    )


@pytest.mark.asyncio
async def test_nats_publisher_publishes_raw_artifact_event() -> None:
    jetstream = FakeJetStream()
    publisher = _publisher(jetstream)
    artifact = RawArtifact(
        artifact_id="art_123",
        run_id="run_123",
        source_id="src_123",
        source_version_id="sv_123",
        storage_path="s3://bucket/runs/run_123/art_123.json",
        content_type="text/html",
        artifact_metadata={"page": 1},
        created_at=datetime(2026, 3, 29, 12, 0, tzinfo=UTC),
    )

    await publisher.publish_raw_artifact_available(artifact)

    subject, payload, headers = jetstream.published[0]
    assert subject == "evidara.raw-artifact-available"
    assert headers is not None
    assert headers["event_type"] == "raw_artifact.available"
    assert headers["artifact_id"] == "art_123"
    event = json.loads(payload)
    assert event["event_type"] == "raw_artifact.available"
    # event_id drives JetStream publish dedup.
    assert headers["Nats-Msg-Id"] == event["event_id"]


@pytest.mark.asyncio
async def test_nats_publisher_publishes_artifact_bundle_event() -> None:
    jetstream = FakeJetStream()
    publisher = _publisher(jetstream)

    await publisher.publish_artifact_bundle_available(
        {
            "event_type": "artifact_bundle.available",
            "event_id": "evt_01kq8000000000000000000001",
            "payload": {
                "bundle_manifest_id": "abm_123",
                "source_snapshot_id": "snap_123",
                "provenance": {
                    "run_id": "run_123",
                    "source_id": "src_123",
                    "source_version_id": "sv_123",
                },
            },
        }
    )

    subject, payload, headers = jetstream.published[0]
    assert subject == "evidara.artifact-bundle-available"
    assert headers is not None
    assert headers["event_type"] == "artifact_bundle.available"
    assert headers["bundle_manifest_id"] == "abm_123"
    assert headers["Nats-Msg-Id"] == "evt_01kq8000000000000000000001"
    assert json.loads(payload)["event_type"] == "artifact_bundle.available"


@pytest.mark.asyncio
async def test_publish_passes_a_bounded_ack_timeout() -> None:
    jetstream = FakeJetStream()
    publisher = NatsRawArtifactPublisher(
        servers="nats://test:4222",
        raw_artifact_subject="evidara.raw-artifact-available",
        artifact_bundle_subject="evidara.artifact-bundle-available",
        jetstream=jetstream,
        publish_timeout_seconds=3.0,
    )
    await publisher.publish_artifact_bundle_available(
        {
            "event_type": "artifact_bundle.available",
            "event_id": "evt_01kq8000000000000000000002",
            "payload": {
                "bundle_manifest_id": "abm_123",
                "source_snapshot_id": "snap_123",
                "provenance": {
                    "run_id": "run_123",
                    "source_id": "src_123",
                    "source_version_id": "sv_123",
                },
            },
        }
    )
    assert jetstream.timeouts == [3.0]


@pytest.mark.asyncio
async def test_connect_is_bounded_and_the_error_reaches_the_caller(monkeypatch) -> None:
    """An unreachable broker must fail in seconds, not minutes (#722).

    The dispatch path answers an operator over HTTP. #707/#721 made a failed publish
    record the run `failed` and return 502; this only makes it fast. The exception must
    still propagate, because `_publish_pending` catches it to write that record.
    """
    started = asyncio.Event()

    class _HangingNats:
        async def connect(self, *args: Any, **kwargs: Any) -> Any:
            started.set()
            await asyncio.sleep(3600)  # a broker whose DNS never resolves

    monkeypatch.setitem(sys.modules, "nats", _HangingNats())

    publisher = NatsRawArtifactPublisher(
        servers="nats://unreachable:4222",
        raw_artifact_subject="evidara.raw-artifact-available",
        artifact_bundle_subject="evidara.artifact-bundle-available",
        connect_timeout_seconds=0.2,
    )

    loop = asyncio.get_running_loop()
    began = loop.time()
    with pytest.raises(TimeoutError) as excinfo:
        await publisher.publish_artifact_bundle_available(
            {
                "event_type": "artifact_bundle.available",
                "event_id": "evt_01kq8000000000000000000003",
                "payload": {
                    "bundle_manifest_id": "abm_123",
                    "source_snapshot_id": "snap_123",
                    "provenance": {
                        "run_id": "run_123",
                        "source_id": "src_123",
                        "source_version_id": "sv_123",
                    },
                },
            }
        )
    elapsed = loop.time() - began

    assert started.is_set()
    assert elapsed < 2.0, f"connect was not bounded: took {elapsed:.1f}s"
    assert "unreachable" in str(excinfo.value)


@pytest.mark.asyncio
async def test_a_down_broker_costs_the_connect_ceiling_once_per_batch(monkeypatch) -> None:
    """The per-event ceiling must not multiply by the batch size (#722).

    `_publish_pending_dispatch_events` publishes each event independently (#707), so
    without a cooldown a 500-artifact run against a down broker would pay 500 x the
    connect timeout — slower than the bug being fixed.
    """
    attempts = 0

    class _HangingNats:
        async def connect(self, *args: Any, **kwargs: Any) -> Any:
            nonlocal attempts
            attempts += 1
            await asyncio.sleep(3600)

    monkeypatch.setitem(sys.modules, "nats", _HangingNats())

    publisher = NatsRawArtifactPublisher(
        servers="nats://unreachable:4222",
        raw_artifact_subject="evidara.raw-artifact-available",
        artifact_bundle_subject="evidara.artifact-bundle-available",
        connect_timeout_seconds=0.2,
        connect_cooldown_seconds=30.0,
    )

    def _event(index: int) -> dict[str, Any]:
        return {
            "event_type": "artifact_bundle.available",
            "event_id": f"evt_batch_{index}",
            "payload": {
                "bundle_manifest_id": "abm_123",
                "source_snapshot_id": "snap_123",
                "provenance": {
                    "run_id": "run_123",
                    "source_id": "src_123",
                    "source_version_id": "sv_123",
                },
            },
        }

    loop = asyncio.get_running_loop()
    began = loop.time()
    for index in range(20):
        with pytest.raises(TimeoutError):
            await publisher.publish_artifact_bundle_available(_event(index))
    elapsed = loop.time() - began

    # One real attempt for the batch; the other 19 fail instantly from the cooldown.
    assert attempts == 1
    assert elapsed < 1.0, f"batch cost scaled with size: {elapsed:.1f}s for 20 events"
