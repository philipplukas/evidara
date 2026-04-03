from __future__ import annotations

from platform_control.config import Settings
from platform_control.integrations import get_artifact_store
from platform_control.services.artifact_store import GcsArtifactStore, LocalArtifactStore


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
