"""Unit tests for the S3/MinIO bundle loader and dispatch routing (ADR-0029 Slice 4)."""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from document_intelligence.contracts.envelope import ManifestRef
from document_intelligence.ingest.loaders import (
    BundleLoader,
    BundleLoadError,
    DispatchingBundleLoader,
    S3BundleLoader,
    _parse_s3_uri,
)
from support import build_manifest_payload

_BUCKET = "evidara-raw-artifacts-prod"
_KEY = "runs/run_x/manifest.json"
_S3_URI = f"s3://{_BUCKET}/{_KEY}"


class FakeS3Client:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self.requested: list[tuple[str, str]] = []

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:  # noqa: N803
        self.requested.append((Bucket, Key))
        return {"Body": io.BytesIO(self._payload)}


def _manifest_ref(uri: str, manifest_bytes: bytes, *, checksum: str | None = None) -> ManifestRef:
    return ManifestRef.from_dict(
        {
            "manifest_id": "abm_01jq7ab8x4nm7m3qz3b8e9q2fk",
            "manifest_type": "artifact_bundle_manifest",
            "manifest_version": 1,
            "storage_ref": {
                "uri": uri,
                "content_type": "application/json",
                "byte_size": len(manifest_bytes),
                "checksum": checksum or hashlib.sha256(manifest_bytes).hexdigest(),
                "checksum_algorithm": "sha256",
            },
        }
    )


class ParseS3UriTests(unittest.TestCase):
    def test_valid_uri_splits_bucket_and_key(self) -> None:
        self.assertEqual(_parse_s3_uri("s3://bucket/path/to/object.json"), ("bucket", "path/to/object.json"))

    def test_missing_key_is_rejected(self) -> None:
        with self.assertRaises(BundleLoadError):
            _parse_s3_uri("s3://only-bucket")

    def test_non_s3_scheme_is_rejected(self) -> None:
        with self.assertRaises(BundleLoadError):
            _parse_s3_uri("gs://bucket/object")


class S3BundleLoaderTests(unittest.TestCase):
    def test_loads_bundle_from_s3_and_verifies_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_path = os.path.join(temp_dir, "doc.html")
            Path(artifact_path).write_text(
                "<html><head><title>S3 Doc</title></head><body><h1>Intro</h1><p>Body</p></body></html>",
                encoding="utf-8",
            )
            manifest_dict = build_manifest_payload(artifact_path, artifact_role="primary_document")
            manifest_bytes = json.dumps(manifest_dict, sort_keys=True).encode("utf-8")

            client = FakeS3Client(manifest_bytes)
            loader = S3BundleLoader(client_factory=lambda: client)
            bundle = loader.load_bundle(_manifest_ref(_S3_URI, manifest_bytes))

        self.assertEqual(bundle.primary_artifact.artifact_role, "primary_document")
        self.assertEqual(client.requested, [(_BUCKET, _KEY)])

    def test_checksum_mismatch_raises(self) -> None:
        manifest_bytes = b'{"bundle_manifest_id":"abm_x"}'
        client = FakeS3Client(manifest_bytes)
        loader = S3BundleLoader(client_factory=lambda: client)
        ref = _manifest_ref(_S3_URI, manifest_bytes, checksum="0" * 64)

        with self.assertRaises(BundleLoadError):
            loader.load_bundle(ref)


class DispatchRoutingTests(unittest.TestCase):
    def test_s3_uri_routes_to_s3_loader(self) -> None:
        class RecordingLoader(BundleLoader):
            def __init__(self) -> None:
                self.loaded: list[ManifestRef] = []

            def load_bundle(self, manifest_ref: ManifestRef) -> str:
                self.loaded.append(manifest_ref)
                return "SENTINEL"

        recording = RecordingLoader()
        dispatcher = DispatchingBundleLoader(s3_loader=recording)
        ref = _manifest_ref(_S3_URI, b"{}", checksum="0" * 64)  # routing does not verify checksum

        self.assertEqual(dispatcher.load_bundle(ref), "SENTINEL")
        self.assertEqual(len(recording.loaded), 1)


if __name__ == "__main__":
    unittest.main()
