import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from document_intelligence.canonical.models import CommentaryInsight
from document_intelligence.contracts.envelope import ManifestRef
from document_intelligence.ingest.loaders import GcsBundleLoader
from document_intelligence.persist.sinks import DeltaCanonicalSink, DeltaSinkConfig
from document_intelligence.pipeline import ProcessingPipeline
from support import (
    BUNDLE_MANIFEST_ID,
    RUN_ID,
    SOURCE_ID,
    SOURCE_SNAPSHOT_ID,
    SOURCE_VERSION_ID,
    build_bundle_event,
    build_manifest_payload,
)

DELTA_AVAILABLE = importlib.util.find_spec("deltalake") is not None


class GcsBundleLoaderTests(unittest.TestCase):
    def test_loads_manifest_and_artifact_via_injected_client(self) -> None:
        html_bytes = b"<html><head><title>GCS Doc</title></head><body><h1>A</h1><p>B</p></body></html>"
        manifest_data = {
            "bundle_manifest_id": BUNDLE_MANIFEST_ID,
            "manifest_version": 1,
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
            "source_snapshot_id": SOURCE_SNAPSHOT_ID,
            "snapshot_external_id": "fedlex:2024-03-01:sr-101",
            "upstream_locator": "https://www.fedlex.admin.ch/eli/cc/1999/404/de",
            "source_origin_kind": "official_primary",
            "trust_tier": "authoritative",
            "snapshot_captured_at": "2026-03-29T09:30:00Z",
            "source_defaults": {"jurisdiction_id": "jur_ch_federal"},
            "parser_hints": {
                "expected_modalities": ["html"],
                "expected_content_types": ["text/html"],
                "preferred_primary_artifact_roles": ["primary_document"],
            },
            "reference_context": {
                "reference_snapshot_policy": "latest_approved",
                "reference_snapshot_set_ref": None,
            },
            "artifacts": [
                {
                    "artifact_id": "art_01jq7af3f8qqc46zc6xvkf9y4x",
                    "artifact_role": "primary_document",
                    "storage_ref": {
                        "uri": "gs://bucket/primary.html",
                        "content_type": "text/html",
                        "byte_size": len(html_bytes),
                        "checksum": hashlib.sha256(html_bytes).hexdigest(),
                        "checksum_algorithm": "sha256",
                        "created_at": "2026-03-29T09:30:05Z",
                    },
                }
            ],
            "di_overrides": {},
            "bundle_metadata": {},
        }
        manifest_bytes = json.dumps(manifest_data).encode("utf-8")

        loader = GcsBundleLoader(
            client_factory=lambda: FakeStorageClient(
                {
                    ("bucket", "bundle-manifest.json"): manifest_bytes,
                    ("bucket", "primary.html"): html_bytes,
                }
            )
        )

        manifest_ref = ManifestRef.from_dict(
            {
                "manifest_id": manifest_data["bundle_manifest_id"],
                "manifest_type": "artifact_bundle_manifest",
                "manifest_version": 1,
                "storage_ref": {
                    "uri": "gs://bucket/bundle-manifest.json",
                    "content_type": "application/json",
                    "byte_size": len(manifest_bytes),
                    "checksum": hashlib.sha256(manifest_bytes).hexdigest(),
                    "checksum_algorithm": "sha256",
                    "created_at": "2026-03-29T09:30:05Z",
                },
            }
        )

        selected_bundle = loader.load_bundle(manifest_ref)
        artifact_text = loader.read_artifact_text(selected_bundle.primary_artifact)

        self.assertEqual(selected_bundle.primary_artifact.artifact_role, "primary_document")
        self.assertIn("GCS Doc", artifact_text)


@unittest.skipUnless(DELTA_AVAILABLE, "deltalake is not installed")
class DeltaReadyRowsTests(unittest.TestCase):
    def test_projects_rows_to_published_surface_columns(self) -> None:
        from document_intelligence.persist.sinks import (
            _PROCESSING_MANIFESTS_DELTA_KEYS,
            _delta_ready_rows,
        )

        rows = [{"processing_manifest_id": "m1", "manifest_version": 1, "noise": "drop-me"}]
        out = _delta_ready_rows(rows, always_present_keys=_PROCESSING_MANIFESTS_DELTA_KEYS)
        self.assertNotIn("noise", out[0])
        self.assertIsNone(out[0]["published_document_ref"])


@unittest.skipUnless(DELTA_AVAILABLE, "deltalake is not installed")
class DeltaCanonicalSinkTests(unittest.TestCase):
    def test_writes_contract_rows_to_delta_tables(self) -> None:
        import deltalake

        with tempfile.TemporaryDirectory() as temp_dir:
            result = build_processing_result()
            sink = DeltaCanonicalSink(
                DeltaSinkConfig(
                    published_documents_uri=os.path.join(temp_dir, "published_documents"),
                    published_sections_uri=os.path.join(temp_dir, "published_sections"),
                    processing_manifests_uri=os.path.join(temp_dir, "processing_manifests"),
                )
            )

            sink.persist(result.document, result.sections, result.manifest)
            sink.record_status_events(result.status_events)
            sink.record_document_processed_event(result.document_processed_event)

            document_rows = (
                deltalake.DeltaTable(os.path.join(temp_dir, "published_documents")).to_pyarrow_table().to_pylist()
            )
            section_rows = (
                deltalake.DeltaTable(os.path.join(temp_dir, "published_sections")).to_pyarrow_table().to_pylist()
            )
            manifest_rows = (
                deltalake.DeltaTable(os.path.join(temp_dir, "processing_manifests")).to_pyarrow_table().to_pylist()
            )

            self.assertEqual(len(document_rows), 1)
            self.assertEqual(len(section_rows), len(result.sections))
            self.assertEqual(len(manifest_rows), 1)
            self.assertEqual(document_rows[0]["document_id"], result.document.document_id)
            self.assertEqual(document_rows[0]["extensions"], result.document.extensions)
            self.assertEqual(
                manifest_rows[0]["published_document_ref"]["surface_name"],
                "published_documents",
            )
            self.assertEqual(len(sink.status_events), 3)
            self.assertEqual(len(sink.document_processed_events), 1)

    def test_replay_appends_new_manifest_rows_while_document_identity_stays_stable(
        self,
    ) -> None:
        import deltalake

        with tempfile.TemporaryDirectory() as temp_dir:
            sink = DeltaCanonicalSink(
                DeltaSinkConfig(
                    published_documents_uri=os.path.join(temp_dir, "published_documents"),
                    published_sections_uri=os.path.join(temp_dir, "published_sections"),
                    processing_manifests_uri=os.path.join(temp_dir, "processing_manifests"),
                )
            )
            first = build_processing_result()
            second = build_processing_result()

            sink.persist(first.document, first.sections, first.manifest)
            sink.persist(second.document, second.sections, second.manifest)

            document_rows = (
                deltalake.DeltaTable(os.path.join(temp_dir, "published_documents")).to_pyarrow_table().to_pylist()
            )
            manifest_rows = (
                deltalake.DeltaTable(os.path.join(temp_dir, "processing_manifests")).to_pyarrow_table().to_pylist()
            )

            self.assertEqual(first.document.document_id, second.document.document_id)
            self.assertNotEqual(
                first.manifest.processing_manifest_id,
                second.manifest.processing_manifest_id,
            )
            self.assertEqual(len(document_rows), 2)
            self.assertEqual(len(manifest_rows), 2)

    def test_writes_commentary_insights_to_delta_table(self) -> None:
        import deltalake

        with tempfile.TemporaryDirectory() as temp_dir:
            sink = DeltaCanonicalSink(
                DeltaSinkConfig(
                    published_documents_uri=os.path.join(temp_dir, "published_documents"),
                    published_sections_uri=os.path.join(temp_dir, "published_sections"),
                    processing_manifests_uri=os.path.join(temp_dir, "processing_manifests"),
                    published_commentary_insights_uri=os.path.join(
                        temp_dir,
                        "published_commentary_insights",
                    ),
                )
            )

            sink.persist_commentary_insights([build_commentary_insight()])

            insight_rows = (
                deltalake.DeltaTable(os.path.join(temp_dir, "published_commentary_insights"))
                .to_pyarrow_table()
                .to_pylist()
            )

            self.assertEqual(len(insight_rows), 1)
            self.assertEqual(insight_rows[0]["insight_id"], "ins_01jq7c1ny0ffv8qdr1xwbejqb6")

    def test_schema_merge_allows_extensions_to_appear_after_non_citation_rows(self) -> None:
        import deltalake

        with tempfile.TemporaryDirectory() as temp_dir:
            sink = DeltaCanonicalSink(
                DeltaSinkConfig(
                    published_documents_uri=os.path.join(temp_dir, "published_documents"),
                    published_sections_uri=os.path.join(temp_dir, "published_sections"),
                    processing_manifests_uri=os.path.join(temp_dir, "processing_manifests"),
                )
            )
            uncited = build_processing_result(
                html=(
                    "<html><head><title>No Citation Doc</title></head>"
                    "<body><h1>One</h1><p>Body without legal references.</p></body></html>"
                )
            )
            sink.persist(uncited.document, uncited.sections, uncited.manifest)
            cited = build_processing_result()
            sink.persist(cited.document, cited.sections, cited.manifest)

            document_rows = (
                deltalake.DeltaTable(os.path.join(temp_dir, "published_documents")).to_pyarrow_table().to_pylist()
            )

            self.assertEqual(len(document_rows), 2)
            self.assertEqual(sum(1 for row in document_rows if row.get("extensions") is None), 1)
            self.assertEqual(
                sum(1 for row in document_rows if len((row.get("extensions") or {}).get("citations") or []) > 0),
                1,
            )


def build_processing_result(
    *,
    html: str = (
        "<html><head><title>Delta Doc</title></head>"
        "<body><h1>One</h1><p>Body cites BGBl. Nr. 43/1975.</p></body></html>"
    ),
):
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as html_handle:
        html_handle.write(html)
        artifact_path = html_handle.name

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_handle:
        json.dump(
            build_manifest_payload(
                artifact_path,
                artifact_role="primary_document",
            ),
            manifest_handle,
        )
        manifest_path = manifest_handle.name

    try:
        return ProcessingPipeline(processing_version="di_2026_03_29").process_event(build_bundle_event(manifest_path))
    finally:
        os.unlink(artifact_path)
        os.unlink(manifest_path)


def build_commentary_insight() -> CommentaryInsight:
    return CommentaryInsight(
        insight_id="ins_01jq7c1ny0ffv8qdr1xwbejqb6",
        document_id="doc_01jq7bdptzqv3xs0c41xpw1ybg",
        document_revision=1,
        processing_manifest_id="pm_01jq7bhgy7g0pkj4f1d03f8f8c",
        section_id="sec_01jq7bprm7p1ef4rwr7s2j1bt3",
        citation_id=None,
        insight_type="referenced_provision",
        claim="References Art. 754 OR",
        display_text="Art. 754 OR wird in der Lehre erlaeutert.",
        support=[
            {
                "document_id": "doc_01jq7bdptzqv3xs0c41xpw1ybg",
                "section_id": "sec_01jq7bprm7p1ef4rwr7s2j1bt3",
                "citation_id": None,
                "ref_type": "passage",
                "passage": "Art. 754 OR wird in der Lehre erlaeutert.",
                "confidence": 0.78,
                "metadata": {"source": "test"},
            }
        ],
        referenced_authorities=[
            {
                "text": "Art. 754 OR",
                "citation_type": "article",
                "metadata": {},
            }
        ],
        language="de",
        jurisdiction_id="jur_ch_federal",
        confidence=0.78,
        review_state="machine_verified",
        generator={
            "name": "commentary-insight-extractor",
            "version": "v1",
            "model": None,
            "prompt_version": None,
        },
        scores={
            "passage_present": 1.0,
            "citation_parseable": 1.0,
            "section_anchor_resolved": 1.0,
        },
        metadata={"extractive": True},
    )


class FakeStorageClient:
    def __init__(self, payloads):
        self._payloads = payloads

    def bucket(self, bucket_name):
        return FakeBucket(bucket_name, self._payloads)


class FakeBucket:
    def __init__(self, bucket_name, payloads):
        self._bucket_name = bucket_name
        self._payloads = payloads

    def blob(self, object_name):
        return FakeBlob(self._payloads[(self._bucket_name, object_name)])


class FakeBlob:
    def __init__(self, payload):
        self._payload = payload

    def download_as_bytes(self):
        return self._payload


if __name__ == "__main__":
    unittest.main()
