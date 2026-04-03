from __future__ import annotations

from platform_control.config import Settings
from platform_control.integrations import get_artifact_store
from platform_control.services.artifact_store import GcsArtifactStore, LocalArtifactStore


def test_get_artifact_store_defaults_to_local_backend() -> None:
    settings = Settings()

    store = get_artifact_store(settings)

    assert isinstance(store, LocalArtifactStore)


def test_get_artifact_store_builds_gcs_backend_from_settings() -> None:
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
