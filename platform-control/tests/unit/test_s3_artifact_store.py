from __future__ import annotations

import json

import pytest

from platform_control.services.artifact_store import S3ArtifactStore


class FakeS3Client:
    def __init__(self) -> None:
        self.put_calls: list[dict[str, object]] = []
        self.deleted: list[tuple[str, str]] = []

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:  # noqa: N803
        self.put_calls.append(
            {"Bucket": Bucket, "Key": Key, "Body": Body, "ContentType": ContentType}
        )

    def delete_object(self, *, Bucket: str, Key: str) -> None:  # noqa: N803
        self.deleted.append((Bucket, Key))


def _store(client: FakeS3Client) -> S3ArtifactStore:
    return S3ArtifactStore(
        bucket_name="evidara-raw-artifacts-prod",
        object_prefix="runs",
        s3_client=client,
    )


@pytest.mark.asyncio
async def test_store_page_payload_uploads_and_returns_s3_uri() -> None:
    client = FakeS3Client()
    store = _store(client)

    uri = await store.store_page_payload("run_123", "art_123", {"page": 1})

    assert uri == "s3://evidara-raw-artifacts-prod/runs/run_123/art_123.json"
    call = client.put_calls[0]
    assert call["Bucket"] == "evidara-raw-artifacts-prod"
    assert call["Key"] == "runs/run_123/art_123.json"
    assert call["ContentType"] == "application/json"
    assert json.loads(call["Body"]) == {"page": 1}


@pytest.mark.asyncio
async def test_store_bundle_manifest_returns_storage_ref() -> None:
    client = FakeS3Client()
    store = _store(client)

    ref = await store.store_bundle_manifest("run_123", "abm_123", {"bundle": True})

    assert ref["uri"] == "s3://evidara-raw-artifacts-prod/runs/run_123/abm_123.json"
    assert ref["content_type"] == "application/json"
    assert ref["checksum_algorithm"] == "sha256"
    assert ref["byte_size"] == len(client.put_calls[0]["Body"])


@pytest.mark.asyncio
async def test_delete_blob_targets_matching_bucket_only() -> None:
    client = FakeS3Client()
    store = _store(client)

    await store.delete_blob("s3://evidara-raw-artifacts-prod/runs/run_123/art_123.json")
    await store.delete_blob("gs://other-bucket/runs/run_123/art_123.json")  # ignored

    assert client.deleted == [("evidara-raw-artifacts-prod", "runs/run_123/art_123.json")]


def test_empty_bucket_name_is_rejected() -> None:
    from platform_control.errors import IntegrationConfigurationError

    with pytest.raises(IntegrationConfigurationError):
        S3ArtifactStore(bucket_name="", s3_client=FakeS3Client())
