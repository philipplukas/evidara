from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol

from google.cloud import storage

from platform_control.config import get_settings
from platform_control.errors import IntegrationConfigurationError


class ArtifactStore(Protocol):
    async def store_page_payload(
        self,
        run_id: str,
        artifact_id: str,
        payload: dict[str, Any],
    ) -> str: ...

    async def store_bundle_manifest(
        self,
        run_id: str,
        bundle_manifest_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]: ...


class LocalArtifactStore:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or get_settings().raw_artifact_local_dir

    async def store_page_payload(
        self,
        run_id: str,
        artifact_id: str,
        payload: dict[str, Any],
    ) -> str:
        artifact_dir = self.base_dir / run_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / f"{artifact_id}.json"
        artifact_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return f"file://{artifact_path.resolve()}"

    async def store_bundle_manifest(
        self,
        run_id: str,
        bundle_manifest_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        artifact_dir = self.base_dir / run_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / f"{bundle_manifest_id}.json"
        payload_bytes = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        artifact_path.write_bytes(payload_bytes)
        return _build_storage_ref(
            f"file://{artifact_path.resolve()}",
            "application/json",
            payload_bytes,
        )


class GcsArtifactStore:
    def __init__(
        self,
        *,
        bucket_name: str,
        object_prefix: str = "runs",
        project_id: str | None = None,
        storage_client: storage.Client | Any | None = None,
    ) -> None:
        if not bucket_name:
            raise IntegrationConfigurationError("Raw artifact bucket name must be configured.")
        self.bucket_name = bucket_name
        self.object_prefix = object_prefix.strip("/")
        self.storage_client = storage_client or storage.Client(project=project_id)

    async def store_page_payload(
        self,
        run_id: str,
        artifact_id: str,
        payload: dict[str, Any],
    ) -> str:
        object_name = self._build_object_name(run_id, artifact_id)
        payload_bytes = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")

        def _upload() -> str:
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(object_name)
            blob.upload_from_string(payload_bytes, content_type="application/json")
            return f"gs://{self.bucket_name}/{object_name}"

        return await asyncio.to_thread(_upload)

    async def store_bundle_manifest(
        self,
        run_id: str,
        bundle_manifest_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        object_name = self._build_object_name(run_id, bundle_manifest_id)
        payload_bytes = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")

        def _upload() -> dict[str, Any]:
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(object_name)
            blob.upload_from_string(payload_bytes, content_type="application/json")
            uri = f"gs://{self.bucket_name}/{object_name}"
            return _build_storage_ref(uri, "application/json", payload_bytes)

        return await asyncio.to_thread(_upload)

    def _build_object_name(self, run_id: str, artifact_id: str) -> str:
        if self.object_prefix:
            return f"{self.object_prefix}/{run_id}/{artifact_id}.json"
        return f"{run_id}/{artifact_id}.json"


def _build_storage_ref(uri: str, content_type: str, payload_bytes: bytes) -> dict[str, Any]:
    return {
        "uri": uri,
        "content_type": content_type,
        "byte_size": len(payload_bytes),
        "checksum": hashlib.sha256(payload_bytes).hexdigest(),
        "checksum_algorithm": "sha256",
    }
