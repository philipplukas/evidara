import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from document_intelligence.contracts.envelope import (
    ArtifactBundleAvailableEvent,
    ArtifactBundleManifest,
    EnvelopeError,
)
from document_intelligence.ingest.loaders import (
    BundleLoadError,
    LocalFilesystemBundleLoader,
)
from document_intelligence.validate.schema_validation import (
    build_contract_validator,
    load_contract_example,
    validate_instance_against_contract,
)
from support import (
    BUNDLE_MANIFEST_ID,
    EVENT_ID,
    RUN_ID,
    SOURCE_ID,
    SOURCE_SNAPSHOT_ID,
    SOURCE_VERSION_ID,
    build_bundle_event,
    build_manifest_payload,
)


class ArtifactBundleAvailableEventTests(unittest.TestCase):
    def test_parses_current_contract_shape(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_handle:
            json.dump({"placeholder": True}, manifest_handle)
            manifest_path = manifest_handle.name

        try:
            event = ArtifactBundleAvailableEvent.from_dict(
                {
                    "event_type": "artifact_bundle.available",
                    "event_version": 1,
                    "event_id": EVENT_ID,
                    "occurred_at": "2026-03-29T12:00:00Z",
                    "producer": "platform-control",
                    "correlation_id": RUN_ID,
                    "payload": {
                        "bundle_manifest_id": BUNDLE_MANIFEST_ID,
                        "source_snapshot_id": SOURCE_SNAPSHOT_ID,
                        "provenance": {
                            "tenant_id": "tenant_public",
                            "corpus_id": "corpus_public_ch_federal_law",
                            "scope_type": "global_public",
                            "source_id": SOURCE_ID,
                            "source_version_id": SOURCE_VERSION_ID,
                            "run_id": RUN_ID,
                            "source_snapshot_id": SOURCE_SNAPSHOT_ID,
                            "bundle_manifest_id": BUNDLE_MANIFEST_ID,
                        },
                        "source_origin_kind": "official_primary",
                        "trust_tier": "authoritative",
                        "bundle_manifest_ref": {
                            "manifest_id": BUNDLE_MANIFEST_ID,
                            "manifest_type": "artifact_bundle_manifest",
                            "manifest_version": 1,
                            "storage_ref": {
                                "uri": f"file://{manifest_path}",
                                "content_type": "application/json",
                                "byte_size": 18,
                                "checksum": "24e6ec454d00f7a8e7b676f6f1668d7875504c731d087f75f66e905b00d69a6a",
                                "checksum_algorithm": "sha256",
                            },
                        },
                        "extra_payload_field": "kept-for-later",
                    },
                    "extra_event_field": "also-preserved",
                }
            )
        finally:
            os.unlink(manifest_path)

        self.assertEqual(event.payload.bundle_manifest_id, BUNDLE_MANIFEST_ID)
        self.assertEqual(event.payload.provenance.source_version_id, SOURCE_VERSION_ID)
        self.assertEqual(event.payload.extra_fields["extra_payload_field"], "kept-for-later")
        self.assertEqual(event.extra_fields["extra_event_field"], "also-preserved")

    def test_parses_manifest_with_primary_html_artifact(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as artifact_handle:
            artifact_handle.write("<html><body>Hello</body></html>")
            artifact_path = artifact_handle.name

        try:
            manifest = ArtifactBundleManifest.from_dict(
                build_manifest_payload(
                    artifact_path,
                    artifact_role="primary_document",
                )
            )
        finally:
            os.unlink(artifact_path)

        self.assertEqual(manifest.artifacts[0].artifact_role, "primary_document")
        self.assertEqual(manifest.artifacts[0].storage_ref.content_type, "text/html")

    def test_raises_for_missing_required_payload_fields(self) -> None:
        with self.assertRaises(EnvelopeError):
            ArtifactBundleAvailableEvent.from_dict({"payload": {"bundle_manifest_id": BUNDLE_MANIFEST_ID}})

    def test_rejects_manifest_without_selectable_primary_artifact(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as artifact_handle:
            json.dump({"metadata": True}, artifact_handle)
            artifact_path = artifact_handle.name

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(
                build_manifest_payload(
                    artifact_path,
                    artifact_role="metadata",
                    content_type="application/json",
                    parser_hints={"preferred_primary_artifact_roles": []},
                ),
                handle,
            )
            manifest_path = handle.name

        try:
            loader = LocalFilesystemBundleLoader()
            with self.assertRaises(BundleLoadError):
                loader.load_bundle(
                    ArtifactBundleAvailableEvent.from_dict(
                        build_bundle_event(manifest_path)
                    ).payload.bundle_manifest_ref
                )
        finally:
            os.unlink(manifest_path)
            os.unlink(artifact_path)


class ContractSchemaValidationTests(unittest.TestCase):
    def test_validates_repo_examples_against_offline_schema_registry(self) -> None:
        example_to_schema = {
            "artifact-bundle-available.json": "events/artifact-bundle-available.schema.json",
            "artifact-bundle-manifest.json": "schemas/artifact-bundle-manifest.schema.json",
            "document.json": "schemas/document.schema.json",
            "document-processed.json": "events/document-processed.schema.json",
            "document-processing-status-updated.json": "events/document-processing-status-updated.schema.json",
            "document-withdrawn.json": "events/document-withdrawn.schema.json",
            "processing-manifest.json": "schemas/processing-manifest.schema.json",
            "section.json": "schemas/section.schema.json",
        }

        for example_name, schema_path in example_to_schema.items():
            with self.subTest(example=example_name):
                validate_instance_against_contract(
                    load_contract_example(example_name),
                    schema_path,
                )

    def test_builds_validator_with_local_refs_only(self) -> None:
        validator = build_contract_validator("events/document-processed.schema.json")
        validator.validate(load_contract_example("document-processed.json"))

        withdrawn_validator = build_contract_validator("events/document-withdrawn.schema.json")
        withdrawn_validator.validate(load_contract_example("document-withdrawn.json"))


if __name__ == "__main__":
    unittest.main()
