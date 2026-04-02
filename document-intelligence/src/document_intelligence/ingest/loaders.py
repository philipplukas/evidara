"""Bundle manifest and artifact loaders for local and GCS-backed processing."""

import hashlib
import importlib
import json
import os
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from document_intelligence.contracts.envelope import (
    ArtifactBundleManifest,
    ArtifactBundleManifestArtifact,
    ManifestRef,
)
from document_intelligence.errors import ProcessingError


class BundleLoadError(ProcessingError):
    """Raised when a bundle manifest or artifact cannot be loaded safely."""


@dataclass(frozen=True)
class SelectedArtifactBundle:
    manifest: ArtifactBundleManifest
    primary_artifact: ArtifactBundleManifestArtifact
    sibling_artifacts: List[ArtifactBundleManifestArtifact]


class BundleLoader:
    """Interface for loading bundle manifests and artifacts."""

    def load_bundle(self, manifest_ref: ManifestRef) -> SelectedArtifactBundle:
        raise NotImplementedError

    def read_artifact_text(self, artifact: ArtifactBundleManifestArtifact) -> str:
        raise NotImplementedError


class DispatchingBundleLoader(BundleLoader):
    """Route bundle reads to the appropriate loader based on URI scheme."""

    def __init__(
        self,
        *,
        local_loader: Optional[BundleLoader] = None,
        gcs_loader: Optional[BundleLoader] = None,
    ) -> None:
        self._local_loader = local_loader or LocalFilesystemBundleLoader()
        self._gcs_loader = gcs_loader or GcsBundleLoader()

    def load_bundle(self, manifest_ref: ManifestRef) -> SelectedArtifactBundle:
        loader = self._loader_for_uri(_manifest_uri(manifest_ref))
        return loader.load_bundle(manifest_ref)

    def read_artifact_text(self, artifact: ArtifactBundleManifestArtifact) -> str:
        loader = self._loader_for_uri(artifact.storage_ref.uri)
        return loader.read_artifact_text(artifact)

    def _loader_for_uri(self, uri: str) -> BundleLoader:
        if uri.startswith("gs://"):
            return self._gcs_loader
        if uri.startswith("file://") or "://" not in uri:
            return self._local_loader
        raise BundleLoadError(
            "unsupported_storage_scheme",
            "unsupported storage URI scheme for bundle loading: {uri}".format(uri=uri),
        )


class LocalFilesystemBundleLoader(BundleLoader):
    """Development-time local loader for bundle manifests and artifacts."""

    def load_bundle(self, manifest_ref: ManifestRef) -> SelectedArtifactBundle:
        storage_ref = _require_manifest_storage_ref(manifest_ref)
        manifest_path = _resolve_local_path(storage_ref.uri)
        try:
            with open(manifest_path, "rb") as manifest_file:
                manifest_bytes = manifest_file.read()
        except FileNotFoundError as error:
            raise BundleLoadError(
                "missing_manifest",
                "bundle manifest not found at {path}".format(path=manifest_path),
            ) from error
        except OSError as error:
            raise BundleLoadError(
                "unreadable_manifest",
                "bundle manifest could not be read at {path}".format(path=manifest_path),
            ) from error

        _verify_checksum(manifest_bytes, storage_ref, "bundle manifest")
        manifest = _parse_bundle_manifest(manifest_bytes, storage_ref.uri)
        return _build_selected_bundle(manifest)

    def read_artifact_text(self, artifact: ArtifactBundleManifestArtifact) -> str:
        file_path = _resolve_local_path(artifact.storage_ref.uri)
        try:
            with open(file_path, "rb") as artifact_file:
                artifact_bytes = artifact_file.read()
        except FileNotFoundError as error:
            raise BundleLoadError(
                "missing_artifact",
                "artifact not found at {path}".format(path=file_path),
            ) from error
        except OSError as error:
            raise BundleLoadError(
                "unreadable_artifact",
                "artifact could not be read at {path}".format(path=file_path),
            ) from error

        _verify_checksum(artifact_bytes, artifact.storage_ref, "artifact")
        return _decode_text(artifact_bytes, artifact.storage_ref.uri)


class GcsBundleLoader(BundleLoader):
    """Bundle loader backed by the Google Cloud Storage Python client."""

    def __init__(
        self,
        *,
        client_factory: Optional[Callable[[], object]] = None,
    ) -> None:
        self._client_factory = client_factory or _default_gcs_client_factory

    def load_bundle(self, manifest_ref: ManifestRef) -> SelectedArtifactBundle:
        storage_ref = _require_manifest_storage_ref(manifest_ref)
        manifest_bytes = self._download_bytes(storage_ref.uri, "bundle manifest")
        _verify_checksum(manifest_bytes, storage_ref, "bundle manifest")
        manifest = _parse_bundle_manifest(manifest_bytes, storage_ref.uri)
        return _build_selected_bundle(manifest)

    def read_artifact_text(self, artifact: ArtifactBundleManifestArtifact) -> str:
        artifact_bytes = self._download_bytes(artifact.storage_ref.uri, "artifact")
        _verify_checksum(artifact_bytes, artifact.storage_ref, "artifact")
        return _decode_text(artifact_bytes, artifact.storage_ref.uri)

    def _download_bytes(self, uri: str, object_kind: str) -> bytes:
        bucket_name, object_name = _parse_gcs_uri(uri)
        client = self._client_factory()
        try:
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(object_name)
            return blob.download_as_bytes()
        except Exception as error:  # pragma: no cover - client-specific
            raise BundleLoadError(
                "gcs_read_failed",
                "{kind} could not be read from {uri}".format(kind=object_kind, uri=uri),
            ) from error


def _default_gcs_client_factory() -> object:
    try:
        storage_module = importlib.import_module("google.cloud.storage")
    except ModuleNotFoundError as error:  # pragma: no cover - depends on env
        raise BundleLoadError(
            "missing_gcs_dependency",
            "google-cloud-storage is required to read gs:// bundle manifests and artifacts",
        ) from error
    return storage_module.Client()


def _build_selected_bundle(manifest: ArtifactBundleManifest) -> SelectedArtifactBundle:
    primary_artifact = _select_primary_artifact(manifest)
    sibling_artifacts = [
        artifact
        for artifact in manifest.artifacts
        if artifact.artifact_id != primary_artifact.artifact_id
    ]
    return SelectedArtifactBundle(
        manifest=manifest,
        primary_artifact=primary_artifact,
        sibling_artifacts=sibling_artifacts,
    )


def _parse_bundle_manifest(
    manifest_bytes: bytes, source_uri: str
) -> ArtifactBundleManifest:
    try:
        manifest_data = json.loads(manifest_bytes.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise BundleLoadError(
            "invalid_manifest_encoding",
            "bundle manifest at {uri} was not valid UTF-8".format(uri=source_uri),
        ) from error
    except json.JSONDecodeError as error:
        raise BundleLoadError(
            "invalid_manifest_json",
            "bundle manifest at {uri} was not valid JSON".format(uri=source_uri),
        ) from error
    return ArtifactBundleManifest.from_dict(manifest_data)


def _select_primary_artifact(
    manifest: ArtifactBundleManifest,
) -> ArtifactBundleManifestArtifact:
    preferred_roles = list(
        manifest.parser_hints.get("preferred_primary_artifact_roles") or []
    )

    direct_primary = _first_artifact_by_role(manifest.artifacts, "primary_document")
    if direct_primary is not None:
        return direct_primary

    for role in preferred_roles:
        matched = _first_artifact_by_role(manifest.artifacts, role)
        if matched is not None:
            return matched

    for artifact in manifest.artifacts:
        if _is_html_content_type(artifact.storage_ref.content_type):
            return artifact

    raise BundleLoadError(
        "missing_primary_artifact",
        "bundle manifest did not contain a selectable primary artifact",
    )


def _first_artifact_by_role(
    artifacts: List[ArtifactBundleManifestArtifact], role: str
) -> Optional[ArtifactBundleManifestArtifact]:
    for artifact in artifacts:
        if artifact.artifact_role == role:
            return artifact
    return None


def _is_html_content_type(content_type: str) -> bool:
    lowered = (content_type or "").lower()
    return lowered == "text/html" or lowered == "application/xhtml+xml"


def _require_manifest_storage_ref(manifest_ref: ManifestRef):
    if manifest_ref.storage_ref is None:
        raise BundleLoadError(
            "missing_manifest_storage_ref",
            "bundle loader requires a manifest storage_ref",
        )
    return manifest_ref.storage_ref


def _verify_checksum(
    payload: bytes, storage_ref, object_kind: str
) -> None:
    algorithm = (storage_ref.checksum_algorithm or "").lower()
    if algorithm != "sha256":
        raise BundleLoadError(
            "unsupported_checksum_algorithm",
            "{kind} uses unsupported checksum algorithm: {algorithm}".format(
                kind=object_kind, algorithm=storage_ref.checksum_algorithm
            ),
        )
    actual_checksum = hashlib.sha256(payload).hexdigest()
    if actual_checksum != storage_ref.checksum:
        raise BundleLoadError(
            "checksum_mismatch",
            "{kind} checksum mismatch for {uri}".format(
                kind=object_kind, uri=storage_ref.uri
            ),
        )


def _decode_text(payload: bytes, source_uri: str) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise BundleLoadError(
            "invalid_text_encoding",
            "artifact at {uri} was not valid UTF-8 text".format(uri=source_uri),
        ) from error


def _resolve_local_path(uri_or_path: str) -> str:
    if uri_or_path.startswith("file://"):
        return uri_or_path[len("file://") :]
    if "://" in uri_or_path and not uri_or_path.startswith("file://"):
        raise BundleLoadError(
            "unsupported_storage_scheme",
            "only file:// and plain filesystem paths are supported by the local loader",
        )
    return uri_or_path


def _parse_gcs_uri(uri: str) -> Tuple[str, str]:
    if not uri.startswith("gs://"):
        raise BundleLoadError(
            "unsupported_storage_scheme",
            "GCS loader only supports gs:// URIs",
        )
    without_scheme = uri[len("gs://") :]
    bucket_name, _, object_name = without_scheme.partition("/")
    if not bucket_name or not object_name:
        raise BundleLoadError(
            "invalid_gcs_uri",
            "invalid GCS URI: {uri}".format(uri=uri),
        )
    return bucket_name, object_name


def _manifest_uri(manifest_ref: ManifestRef) -> str:
    storage_ref = _require_manifest_storage_ref(manifest_ref)
    return storage_ref.uri

