from __future__ import annotations

from platform_control.config import Settings
from platform_control.integrations import get_artifact_store
from platform_control.services.artifact_store import (
    GcsArtifactStore,
    LocalArtifactStore,
    S3ArtifactStore,
)


class FakeStorageClient:
    def __init__(self, project: str | None = None) -> None:
        self.project = project


def test_get_artifact_store_defaults_to_local_backend() -> None:
    settings = Settings()

    store = get_artifact_store(settings)

    assert isinstance(store, LocalArtifactStore)


def test_get_artifact_store_builds_gcs_backend_from_settings() -> None:
    import platform_control.services.artifact_store as artifact_store_module

    artifact_store_module.storage.Client = FakeStorageClient
    settings = Settings(
        artifact_store_backend="gcs",
        raw_artifact_bucket="evidara-raw-artifacts-staging",
        raw_artifact_prefix="runs",
        gcp_project_id="evidara-staging",
    )

    store = get_artifact_store(settings)

    assert isinstance(store, GcsArtifactStore)
    assert store.bucket_name == "evidara-raw-artifacts-staging"
    assert store.object_prefix == "runs"
    assert isinstance(store.storage_client, FakeStorageClient)
    assert store.storage_client.project == "evidara-staging"


def test_get_artifact_store_builds_s3_backend_from_settings() -> None:
    import platform_control.services.artifact_store as artifact_store_module

    captured: dict[str, object] = {}

    def fake_build_s3_client(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    artifact_store_module._build_s3_client = fake_build_s3_client
    settings = Settings(
        artifact_store_backend="s3",
        raw_artifact_bucket="evidara-raw-artifacts-prod",
        raw_artifact_prefix="runs",
        s3_endpoint_url="http://minio:9000",
        s3_region="us-east-1",
        s3_access_key_id="minio",
        s3_secret_access_key="minio-secret",
    )

    store = get_artifact_store(settings)

    assert isinstance(store, S3ArtifactStore)
    assert store.bucket_name == "evidara-raw-artifacts-prod"
    assert store.object_prefix == "runs"
    assert captured["endpoint_url"] == "http://minio:9000"
    assert captured["access_key_id"] == "minio"
