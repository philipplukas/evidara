"""Unit tests for the S3/MinIO bundle loader and dispatch routing (ADR-0029 Slice 4)."""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from base64 import b64encode
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from document_intelligence.contracts.envelope import ArtifactBundleManifestArtifact, ManifestRef
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


class AcquisitionEnvelopeUnwrapTests(unittest.TestCase):
    """Artifacts are stored as acquisition envelopes but declared as their body's type (#643).

    `acquisition_core.normalization` writes `{"inline_body": "<html>…"}` while the
    manifest says `text/html`. Reading the envelope as the document made the HTML
    normalizer parse JSON-escaped markup, so every non-ASCII character reached
    search as a literal `\\uXXXX` sequence.
    """

    def _read(self, payload: bytes) -> str:
        artifact = ArtifactBundleManifestArtifact.from_dict(
            {
                "artifact_id": "art_01jq7ab8x4nm7m3qz3b8e9q2fk",
                "artifact_role": "primary_document",
                "storage_ref": {
                    "uri": f"s3://{_BUCKET}/runs/run_x/artifact.json",
                    "content_type": "text/html",
                    "byte_size": len(payload),
                    "checksum": hashlib.sha256(payload).hexdigest(),
                    "checksum_algorithm": "sha256",
                },
            }
        )
        client = FakeS3Client(payload)
        return S3BundleLoader(client_factory=lambda: client).read_artifact_text(artifact)

    def _read_bytes(self, payload: bytes) -> bytes:
        artifact = ArtifactBundleManifestArtifact.from_dict(
            {
                "artifact_id": "art_01jq7ab8x4nm7m3qz3b8e9q2fk",
                "artifact_role": "primary_document",
                "storage_ref": {
                    "uri": f"s3://{_BUCKET}/runs/run_x/artifact.json",
                    "content_type": "application/pdf",
                    "byte_size": len(payload),
                    "checksum": hashlib.sha256(payload).hexdigest(),
                    "checksum_algorithm": "sha256",
                },
            }
        )
        client = FakeS3Client(payload)
        return S3BundleLoader(client_factory=lambda: client).read_artifact_bytes(artifact)

    def test_envelope_is_unwrapped_so_non_ascii_survives_as_characters(self) -> None:
        html = "<p>vom 18. April 1999 (Stand am 3. März 2024)</p>"
        envelope = json.dumps({"source_url": "https://example.test/de", "final_url": None, "inline_body": html}).encode(
            "utf-8"
        )
        # ensure_ascii escaped the umlaut on the way in — the bug was keeping it escaped.
        escaped_umlaut = ("M" + chr(92) + "u00e4rz").encode("ascii")
        self.assertIn(escaped_umlaut, envelope)

        self.assertEqual(self._read(envelope), html)

    def test_plain_html_artifact_is_returned_unchanged(self) -> None:
        html = "<p>Präambel</p>"
        self.assertEqual(self._read(html.encode("utf-8")), html)

    def test_json_artifact_without_inline_body_is_returned_unchanged(self) -> None:
        payload = json.dumps({"source_url": "https://example.test"})
        self.assertEqual(self._read(payload.encode("utf-8")), payload)

    def test_brace_leading_text_that_is_not_json_is_returned_unchanged(self) -> None:
        payload = "{not json at all"
        self.assertEqual(self._read(payload.encode("utf-8")), payload)

    def test_binary_envelope_is_base64_decoded_to_the_real_payload(self) -> None:
        # The seam #590 left open: acquisition base64-encodes a PDF into the envelope,
        # and nothing on the read side decoded it — so the PDF normalizer would have
        # received JSON bytes instead of `%PDF-`.
        pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF\n"
        envelope = json.dumps(
            {
                "source_url": "https://example.test/as-554-510.pdf",
                "inline_body_base64": b64encode(pdf).decode("ascii"),
                "inline_body_encoding": "base64",
            }
        ).encode("utf-8")

        self.assertEqual(self._read_bytes(envelope), pdf)

    def test_text_envelope_yields_utf8_bytes_of_the_body(self) -> None:
        html = "<p>Präambel</p>"
        envelope = json.dumps({"inline_body": html, "inline_body_encoding": "utf-8"}).encode("utf-8")
        self.assertEqual(self._read_bytes(envelope), html.encode("utf-8"))

    def test_raw_binary_artifact_passes_through_untouched(self) -> None:
        # A stored PDF that is not enveloped must not be mangled.
        pdf = b"%PDF-1.7\nbinary\x00\xff bytes\n%%EOF"
        self.assertEqual(self._read_bytes(pdf), pdf)

    def test_corrupt_base64_fails_loudly_rather_than_silently(self) -> None:
        envelope = json.dumps({"inline_body_base64": "not!valid!base64!"}).encode("utf-8")
        with self.assertRaises(BundleLoadError) as ctx:
            self._read_bytes(envelope)
        self.assertEqual(ctx.exception.code, "invalid_inline_body_base64")


if __name__ == "__main__":
    unittest.main()
