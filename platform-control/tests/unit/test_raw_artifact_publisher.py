from __future__ import annotations

import json
from base64 import b64encode
from datetime import UTC, datetime

import pytest

from platform_control.events.publisher import PubSubRawArtifactPublisher
from platform_control.events.raw_artifact import build_raw_artifact_event
from platform_control.models.raw_artifact import RawArtifact


class FakePublishFuture:
    def result(self, timeout: int | None = None) -> str:
        del timeout
        return "message-123"


class FakePublisherClient:
    def __init__(self) -> None:
        self.published: list[tuple[str, bytes, dict[str, str]]] = []

    def publish(self, topic_path: str, data: bytes, **attributes: str) -> FakePublishFuture:
        self.published.append((topic_path, data, attributes))
        return FakePublishFuture()


@pytest.mark.asyncio
async def test_pubsub_publisher_builds_raw_artifact_event() -> None:
    publisher_client = FakePublisherClient()
    publisher = PubSubRawArtifactPublisher(
        topic_name="projects/test-project/topics/raw-artifact-available",
        bundle_topic_name="projects/test-project/topics/artifact-bundle-available",
        publisher_client=publisher_client,
    )
    artifact = RawArtifact(
        artifact_id="art_123",
        run_id="run_123",
        source_id="src_123",
        source_version_id="sv_123",
        storage_path="gs://bucket/runs/run_123/art_123.json",
        content_type="text/html",
        artifact_metadata={"page": 1},
        created_at=datetime(2026, 3, 29, 12, 0, tzinfo=UTC),
    )

    await publisher.publish_raw_artifact_available(artifact)

    topic_path, data, attributes = publisher_client.published[0]
    assert topic_path == "projects/test-project/topics/raw-artifact-available"
    assert attributes["event_type"] == "raw_artifact.available"
    assert attributes["artifact_id"] == "art_123"
    assert b'"event_type": "raw_artifact.available"' in data
    assert b'"storage_path": "gs://bucket/runs/run_123/art_123.json"' in data


@pytest.mark.asyncio
async def test_pubsub_publisher_builds_artifact_bundle_event() -> None:
    publisher_client = FakePublisherClient()
    publisher = PubSubRawArtifactPublisher(
        topic_name="projects/test-project/topics/raw-artifact-available",
        bundle_topic_name="projects/test-project/topics/artifact-bundle-available",
        publisher_client=publisher_client,
    )

    await publisher.publish_artifact_bundle_available(
        {
            "event_type": "artifact_bundle.available",
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

    topic_path, data, attributes = publisher_client.published[0]
    assert topic_path == "projects/test-project/topics/artifact-bundle-available"
    assert attributes["event_type"] == "artifact_bundle.available"
    assert attributes["bundle_manifest_id"] == "abm_123"
    assert b'"event_type": "artifact_bundle.available"' in data


# ── #707: the event is a reference, not a transport for the document ─────────


def _artifact_with_inline_body(body: str) -> RawArtifact:
    return RawArtifact(
        artifact_id="art_oversize",
        run_id="run_123",
        source_id="src_123",
        source_version_id="sv_123",
        storage_path="s3://evidara-raw-artifacts/runs/run_123/art_oversize.json",
        content_type="text/html",
        artifact_metadata={
            "source_url": "https://fedlex.data.admin.ch/eli/cc/2008/416/de",
            "final_url": "https://fedlex.data.admin.ch/eli/cc/2008/416/de",
            "title": "Tierschutzverordnung",
            "byte_size": len(body),
            "checksum": "abc123",
            "inline_body": body,
            "inline_body_encoding": "utf-8",
        },
        created_at=datetime(2026, 7, 19, 15, 14, 35, tzinfo=UTC),
    )


def test_raw_artifact_event_omits_the_inline_body_and_keeps_the_storage_reference() -> None:
    artifact = _artifact_with_inline_body("<html>Tierschutzverordnung</html>")

    event = build_raw_artifact_event(artifact)
    metadata = event["payload"]["metadata"]

    # The body is not in the event. It is in the object store, which is what
    # `storage_path` is for and where document-intelligence reads it from.
    assert "inline_body" not in metadata
    assert "inline_body_base64" not in metadata
    assert (
        event["payload"]["storage_path"]
        == "s3://evidara-raw-artifacts/runs/run_123/art_oversize.json"
    )
    # Its absence is stated, not implied — a consumer must not have to guess
    # whether the provider captured nothing (#628).
    assert metadata["inline_body_omitted"] is True
    # Everything that describes the artifact rather than *being* it survives,
    # including what a consumer needs to verify the stored object.
    assert metadata["title"] == "Tierschutzverordnung"
    assert metadata["checksum"] == "abc123"
    assert metadata["inline_body_encoding"] == "utf-8"


def test_event_size_is_independent_of_document_size() -> None:
    """The property that actually fixes #707, stated as a property.

    TSchV's event was 1.23 MB against a 1 MB NATS `max_payload`. Raising the
    broker limit would only move the ceiling — a consolidated code runs to tens
    of megabytes. Publishing a reference removes it: growing the document must
    not grow the event.
    """
    small = build_raw_artifact_event(_artifact_with_inline_body("x" * 1_000))
    # Comfortably past the 1 MB default that broke the original run.
    huge = build_raw_artifact_event(_artifact_with_inline_body("x" * 40_000_000))

    small_size = len(json.dumps(small["payload"]["metadata"]).encode())
    huge_size = len(json.dumps(huge["payload"]["metadata"]).encode())

    # A 40,000x larger document grows the event by a handful of bytes — the extra
    # digits of the `byte_size` integer, and nothing else.
    assert huge_size - small_size < 16
    assert huge_size < 4_096


def test_binary_artifacts_drop_their_base64_body_too() -> None:
    """Municipal PDF ordinances take the `inline_body_base64` branch (#590)."""
    artifact = _artifact_with_inline_body("unused")
    artifact.content_type = "application/pdf"
    artifact.artifact_metadata = {
        "source_url": "https://www.stadt-zuerich.ch/hundereglement.pdf",
        "inline_body_base64": b64encode(b"%PDF-1.7" + b"0" * 2_000_000).decode("ascii"),
        "inline_body_encoding": "base64",
    }

    metadata = build_raw_artifact_event(artifact)["payload"]["metadata"]

    assert "inline_body_base64" not in metadata
    assert metadata["inline_body_omitted"] is True
    assert len(json.dumps(metadata).encode()) < 4_096


def test_metadata_without_an_inline_body_is_passed_through_untouched() -> None:
    """Firecrawl-style artifacts never inlined a body; they must not gain a marker."""
    artifact = _artifact_with_inline_body("unused")
    artifact.artifact_metadata = {"sourceURL": "https://example.com", "statusCode": 200}

    metadata = build_raw_artifact_event(artifact)["payload"]["metadata"]

    assert metadata == {"sourceURL": "https://example.com", "statusCode": 200}
