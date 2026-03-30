from __future__ import annotations

import json

import pytest

from platform_control.services.artifact_store import GcsArtifactStore


class FakeBlob:
    def __init__(self, name: str) -> None:
        self.name = name
        self.uploads: list[tuple[bytes, str | None]] = []

    def upload_from_string(self, payload: bytes, content_type: str | None = None) -> None:
        self.uploads.append((payload, content_type))


class FakeBucket:
    def __init__(self) -> None:
        self.blobs: dict[str, FakeBlob] = {}

    def blob(self, name: str) -> FakeBlob:
        blob = FakeBlob(name)
        self.blobs[name] = blob
        return blob


class FakeStorageClient:
    def __init__(self) -> None:
        self.bucket_requests: list[str] = []
        self.bucket_instance = FakeBucket()

    def bucket(self, bucket_name: str) -> FakeBucket:
        self.bucket_requests.append(bucket_name)
        return self.bucket_instance


@pytest.mark.asyncio
async def test_gcs_artifact_store_uploads_json_payload() -> None:
    client = FakeStorageClient()
    store = GcsArtifactStore(
        bucket_name="evidara-raw-artifacts-dev",
        object_prefix="runs",
        storage_client=client,
    )

    storage_path = await store.store_page_payload(
        run_id="run_123",
        artifact_id="art_456",
        payload={"hello": "world"},
    )

    assert storage_path == "gs://evidara-raw-artifacts-dev/runs/run_123/art_456.json"
    blob = client.bucket_instance.blobs["runs/run_123/art_456.json"]
    payload, content_type = blob.uploads[0]
    assert json.loads(payload.decode("utf-8")) == {"hello": "world"}
    assert content_type == "application/json"
