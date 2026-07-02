"""Bundle manifest and artifact loaders for local, GCS, and S3/MinIO processing."""

import hashlib
import importlib
import json
from collections.abc import Callable
from dataclasses import dataclass

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
    sibling_artifacts: list[ArtifactBundleManifestArtifact]


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
        local_loader: BundleLoader | None = None,
        gcs_loader: BundleLoader | None = None,
        s3_loader: BundleLoader | None = None,
    ) -> None:
        self._local_loader = local_loader or LocalFilesystemBundleLoader()
        self._gcs_loader = gcs_loader or GcsBundleLoader()
        self._s3_loader = s3_loader or S3BundleLoader()

    def load_bundle(self, manifest_ref: ManifestRef) -> SelectedArtifactBundle:
        loader = self._loader_for_uri(_manifest_uri(manifest_ref))
        return loader.load_bundle(manifest_ref)

    def read_artifact_text(self, artifact: ArtifactBundleManifestArtifact) -> str:
        loader = self._loader_for_uri(artifact.storage_ref.uri)
        return loader.read_artifact_text(artifact)

    def _loader_for_uri(self, uri: str) -> BundleLoader:
        if uri.startswith("gs://"):
            return self._gcs_loader
        if uri.startswith("s3://"):
            return self._s3_loader
        if uri.startswith("file://") or "://" not in uri:
            return self._local_loader
        raise BundleLoadError(
            "unsupported_storage_scheme",
            f"unsupported storage URI scheme for bundle loading: {uri}",
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
                f"bundle manifest not found at {manifest_path}",
            ) from error
        except OSError as error:
            raise BundleLoadError(
                "unreadable_manifest",
                f"bundle manifest could not be read at {manifest_path}",
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
                f"artifact not found at {file_path}",
            ) from error
        except OSError as error:
            raise BundleLoadError(
                "unreadable_artifact",
                f"artifact could not be read at {file_path}",
            ) from error

        _verify_checksum(artifact_bytes, artifact.storage_ref, "artifact")
        return _decode_text(artifact_bytes, artifact.storage_ref.uri)


class GcsBundleLoader(BundleLoader):
    """Bundle loader backed by the Google Cloud Storage Python client."""

    def __init__(
        self,
        *,
        client_factory: Callable[[], object] | None = None,
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
                f"{object_kind} could not be read from {uri}",
            ) from error


class S3BundleLoader(BundleLoader):
    """Bundle loader backed by an S3-compatible store (AWS S3 / MinIO, ADR-0029)."""

    def __init__(
        self,
        *,
        client_factory: Callable[[], object] | None = None,
    ) -> None:
        self._client_factory = client_factory or _default_s3_client_factory

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
        bucket_name, object_name = _parse_s3_uri(uri)
        client = self._client_factory()
        try:
            response = client.get_object(Bucket=bucket_name, Key=object_name)
            return response["Body"].read()
        except Exception as error:  # pragma: no cover - client-specific
            raise BundleLoadError(
                "s3_read_failed",
                f"{object_kind} could not be read from {uri}",
            ) from error


def _default_s3_client_factory() -> object:
    import os

    try:
        import boto3
        from botocore.config import Config
    except ModuleNotFoundError as error:  # pragma: no cover - depends on env
        raise BundleLoadError(
            "missing_s3_dependency",
            "boto3 is required to read s3:// bundle manifests and artifacts",
        ) from error

    # Path-style addressing is required for MinIO / custom endpoints.
    kwargs: dict[str, object] = {"config": Config(s3={"addressing_style": "path"})}
    endpoint = os.environ.get("DI_S3_ENDPOINT_URL")
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    region = os.environ.get("DI_S3_REGION")
    if region:
        kwargs["region_name"] = region
    access_key_id = os.environ.get("DI_S3_ACCESS_KEY_ID")
    secret_access_key = os.environ.get("DI_S3_SECRET_ACCESS_KEY")
    if access_key_id and secret_access_key:
        kwargs["aws_access_key_id"] = access_key_id
        kwargs["aws_secret_access_key"] = secret_access_key
    return boto3.client("s3", **kwargs)


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
        artifact for artifact in manifest.artifacts if artifact.artifact_id != primary_artifact.artifact_id
    ]
    return SelectedArtifactBundle(
        manifest=manifest,
        primary_artifact=primary_artifact,
        sibling_artifacts=sibling_artifacts,
    )


def _parse_bundle_manifest(manifest_bytes: bytes, source_uri: str) -> ArtifactBundleManifest:
    try:
        manifest_data = json.loads(manifest_bytes.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise BundleLoadError(
            "invalid_manifest_encoding",
            f"bundle manifest at {source_uri} was not valid UTF-8",
        ) from error
    except json.JSONDecodeError as error:
        raise BundleLoadError(
            "invalid_manifest_json",
            f"bundle manifest at {source_uri} was not valid JSON",
        ) from error
    return ArtifactBundleManifest.from_dict(manifest_data)


_CONTENT_TYPE_PREFERENCE = {
    "application/xml": 0,
    "text/xml": 0,
    "text/html": 1,
    "application/xhtml+xml": 1,
    "application/pdf": 2,
    "text/plain": 3,
}


def _select_primary_artifact(
    manifest: ArtifactBundleManifest,
) -> ArtifactBundleManifestArtifact:
    preferred_roles = list(manifest.parser_hints.get("preferred_primary_artifact_roles") or [])

    direct_primary = _first_artifact_by_role(manifest.artifacts, "primary_document")
    if direct_primary is not None:
        return direct_primary

    for role in preferred_roles:
        matched = _first_artifact_by_role(manifest.artifacts, role)
        if matched is not None:
            return matched

    # Prefer structured formats (XML > HTML > PDF > plain text)
    selectable = [
        a
        for a in manifest.artifacts
        if (a.storage_ref.content_type or "").split(";", 1)[0].strip().lower() in _CONTENT_TYPE_PREFERENCE
    ]
    if selectable:
        selectable.sort(
            key=lambda a: _CONTENT_TYPE_PREFERENCE[(a.storage_ref.content_type or "").split(";", 1)[0].strip().lower()]
        )
        return selectable[0]

    raise BundleLoadError(
        "missing_primary_artifact",
        "bundle manifest did not contain a selectable primary artifact",
    )


def _first_artifact_by_role(
    artifacts: list[ArtifactBundleManifestArtifact], role: str
) -> ArtifactBundleManifestArtifact | None:
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


def _verify_checksum(payload: bytes, storage_ref, object_kind: str) -> None:
    algorithm = (storage_ref.checksum_algorithm or "").lower()
    if algorithm != "sha256":
        raise BundleLoadError(
            "unsupported_checksum_algorithm",
            f"{object_kind} uses unsupported checksum algorithm: {storage_ref.checksum_algorithm}",
        )
    actual_checksum = hashlib.sha256(payload).hexdigest()
    if actual_checksum != storage_ref.checksum:
        raise BundleLoadError(
            "checksum_mismatch",
            f"{object_kind} checksum mismatch for {storage_ref.uri}",
        )


def _decode_text(payload: bytes, source_uri: str) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise BundleLoadError(
            "invalid_text_encoding",
            f"artifact at {source_uri} was not valid UTF-8 text",
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


def _parse_gcs_uri(uri: str) -> tuple[str, str]:
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
            f"invalid GCS URI: {uri}",
        )
    return bucket_name, object_name


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise BundleLoadError(
            "unsupported_storage_scheme",
            "S3 loader only supports s3:// URIs",
        )
    without_scheme = uri[len("s3://") :]
    bucket_name, _, object_name = without_scheme.partition("/")
    if not bucket_name or not object_name:
        raise BundleLoadError(
            "invalid_s3_uri",
            f"invalid S3 URI: {uri}",
        )
    return bucket_name, object_name


def _manifest_uri(manifest_ref: ManifestRef) -> str:
    storage_ref = _require_manifest_storage_ref(manifest_ref)
    return storage_ref.uri
