import dataclasses
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
from document_intelligence.normalize.quarantine import DEFAULT_MIN_LEGAL_MARKERS
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

    def test_quarantine_reason_survives_a_real_delta_write(self) -> None:
        """The reason must survive the *production* sink, not just the in-memory one.

        `_delta_ready_rows` projects every row to exactly `always_present_keys`, so a column
        outside that set is dropped on the way to Delta — which is what happened to the
        quarantine block, invisibly, because `InMemoryCanonicalSink` keeps the whole model
        object and every other test uses it. A quarantine whose slug does not reach storage
        is silent failure with extra steps (ADR-0047 §6), so this test writes a real table
        and reads it back.

        The canonical-ready row is written **first**, deliberately: it pins the other half
        of the bug. Forcing `quarantine`/`failure` always-present makes that row carry a
        PyArrow `null` column, which deltalake refuses outright ("Invalid data type for
        Delta Lake: Null") — so a naive fix trades a lost reason for a dead publish path.
        """
        import deltalake

        with tempfile.TemporaryDirectory() as temp_dir:
            manifests_uri = os.path.join(temp_dir, "processing_manifests")
            sink = DeltaCanonicalSink(
                DeltaSinkConfig(
                    published_documents_uri=os.path.join(temp_dir, "published_documents"),
                    published_sections_uri=os.path.join(temp_dir, "published_sections"),
                    processing_manifests_uri=manifests_uri,
                )
            )

            published = build_processing_result()
            sink.persist(published.document, published.sections, published.manifest)

            quarantined = build_quarantined_processing_result(sink=sink)
            self.assertTrue(quarantined.is_quarantined)

            rows = deltalake.DeltaTable(manifests_uri).to_pyarrow_table().to_pylist()
            by_status = {row["status"]: row for row in rows}
            self.assertEqual(set(by_status), {"canonical_ready", "quarantined"})

            quarantine = by_status["quarantined"]["quarantine"]
            self.assertEqual(quarantine["reason"], "no_text_layer")
            self.assertIn("OCR", quarantine["detail"])
            self.assertEqual(quarantine["extracted_chars"], 0)
            self.assertEqual(quarantine["min_legal_markers"], DEFAULT_MIN_LEGAL_MARKERS)
            # A published row carries no quarantine, and writing it did not fail.
            self.assertIsNone(by_status["canonical_ready"]["quarantine"])

    def test_a_new_metadata_key_survives_append_to_an_existing_table(self) -> None:
        """A canonical metadata key added after the table exists must reach Delta (#836).

        Append casts the batch to the table's own Arrow schema, and that cast reaches into
        `metadata` — a struct column. PyArrow drops a struct field the target type does not
        declare, without error, so `regeste` (and before it `official_citation`,
        `in_force_from`) was written on a fresh table and silently discarded on every append
        to a table created before the key existed. Which is every deployed table.

        The first document is persisted **without** the key, so the table is created from
        the old shape — that is the whole point: starting from an empty directory is what
        made every other test green over this.
        """
        import deltalake

        with tempfile.TemporaryDirectory() as temp_dir:
            documents_uri = os.path.join(temp_dir, "published_documents")
            sink = DeltaCanonicalSink(
                DeltaSinkConfig(
                    published_documents_uri=documents_uri,
                    published_sections_uri=os.path.join(temp_dir, "published_sections"),
                    processing_manifests_uri=os.path.join(temp_dir, "processing_manifests"),
                )
            )

            first = build_processing_result()
            without = dataclasses.replace(
                first.document,
                metadata={k: v for k, v in first.document.metadata.items() if k != "regeste"},
            )
            sink.persist(without, first.sections, first.manifest)
            self.assertNotIn(
                "regeste",
                deltalake.DeltaTable(documents_uri).to_pyarrow_table().to_pylist()[0]["metadata"],
            )

            headnote = "Art. 754 OR; Verantwortlichkeit der Verwaltungsratsmitglieder."
            with_regeste = dataclasses.replace(
                first.document,
                document_id="doc_01hx000000000000000000002x",
                metadata={**without.metadata, "regeste": headnote},
            )
            sink.persist(with_regeste, [], first.manifest)

            rows = {
                row["document_id"]: row for row in deltalake.DeltaTable(documents_uri).to_pyarrow_table().to_pylist()
            }
            self.assertEqual(rows[with_regeste.document_id]["metadata"]["regeste"], headnote)
            # The pre-existing row keeps its shape; widening the schema did not rewrite it.
            self.assertIsNone(rows[without.document_id]["metadata"].get("regeste"))

    def test_a_new_generator_field_survives_a_commentary_insights_write(self) -> None:
        """The second #871 route: one map column was poisoning widening for all of them.

        `published_commentary_insights` is written with a hand-maintained
        `schema_override`, and `generator` is a plain `dict[str, Any]` on the model —
        so a producer adding a key needs no code change at all to hit this.

        The mechanism was NOT that struct widening failed. `pa.unify_schemas` merges
        struct fields correctly. It is all-or-nothing across the schema, and this
        surface declares `metadata` as `map<string, string>` while `from_pylist`
        infers `struct<...>` from the Python dict:

            Unable to merge: Field metadata has incompatible types:
            map<string, string> vs struct<extractive: string>

        That raised on every single write, so the helper returned the un-widened
        schema and `generator`, `support`, `referenced_authorities` and `scores` all
        lost their nested fields as collateral.

        A FRESH table, deliberately — the issue reports this route as worse than the
        append defect because it drops the field even on first write.
        """
        import dataclasses

        import deltalake

        with tempfile.TemporaryDirectory() as temp_dir:
            insights_uri = os.path.join(temp_dir, "published_commentary_insights")
            sink = DeltaCanonicalSink(
                DeltaSinkConfig(
                    published_documents_uri=os.path.join(temp_dir, "published_documents"),
                    published_sections_uri=os.path.join(temp_dir, "published_sections"),
                    processing_manifests_uri=os.path.join(temp_dir, "processing_manifests"),
                    published_commentary_insights_uri=insights_uri,
                )
            )

            base = build_commentary_insight()
            extended = dataclasses.replace(
                base,
                generator={**base.generator, "run_id": "run_xyz"},
            )
            sink.persist_commentary_insights([extended])

            written = deltalake.DeltaTable(insights_uri).to_pyarrow_table().to_pylist()[0]
            self.assertEqual(written["generator"].get("run_id"), "run_xyz")
            # The declared fields are untouched — widening added, it did not replace.
            self.assertEqual(written["generator"]["name"], base.generator["name"])

    def test_an_incompatible_column_does_not_abandon_widening_for_the_others(self) -> None:
        """`metadata` stays a map; that must cost only `metadata` (#871).

        Guard for the per-field unification specifically. Restore the whole-schema
        `pa.unify_schemas` and this fails, because the map/struct conflict returns the
        original schema for every column.
        """
        import pyarrow as pa

        from document_intelligence.persist.sinks import (
            _COMMENTARY_INSIGHTS_ARROW_SCHEMA,
            _widen_for_new_nested_fields,
        )

        rows = [
            {
                "generator": {"name": "x", "version": "v1", "run_id": "run_xyz"},
                # The column that raises on unification: declared map, inferred struct.
                "metadata": {"extractive": "yes"},
            }
        ]
        widened = _widen_for_new_nested_fields(_COMMENTARY_INSIGHTS_ARROW_SCHEMA, rows)

        self.assertIn("run_id", [f.name for f in widened.field("generator").type])
        # The incompatible column keeps its declared type rather than being coerced.
        self.assertEqual(widened.field("metadata").type, pa.map_(pa.string(), pa.string()))
        # And no top-level column was invented.
        self.assertEqual(set(widened.names), set(_COMMENTARY_INSIGHTS_ARROW_SCHEMA.names))

    def test_an_optional_provenance_field_survives_append_to_an_existing_table(self) -> None:
        """The loss is not about `metadata` — it is about every struct column (#871).

        `metadata` is the loudest case because canonical keys are added to it often, but the
        cast that drops a nested field is applied to `provenance` too, and that one needs no
        code change to bite: `Provenance.to_dict` omits its optional fields when they are
        `None`, so the struct the table is *created* with is whatever the first row happened
        to carry. A first document acquired without a `source_snapshot_id` therefore freezes
        `provenance` without that field, and every later document's snapshot id — its link
        back to the exact upstream capture — is dropped on the way to Delta.

        Which restates the exposure correctly: not "keys added after the table was created",
        but "keys absent from the batch that created the table".
        """
        import deltalake

        with tempfile.TemporaryDirectory() as temp_dir:
            documents_uri = os.path.join(temp_dir, "published_documents")
            sink = DeltaCanonicalSink(
                DeltaSinkConfig(
                    published_documents_uri=documents_uri,
                    published_sections_uri=os.path.join(temp_dir, "published_sections"),
                    processing_manifests_uri=os.path.join(temp_dir, "processing_manifests"),
                )
            )

            first = build_processing_result()
            self.assertEqual(first.document.provenance.source_snapshot_id, SOURCE_SNAPSHOT_ID)
            # Create the table from a document whose provenance carries no snapshot id.
            without = dataclasses.replace(
                first.document,
                provenance=first.document.provenance.with_updates(source_snapshot_id=None),
            )
            sink.persist(without, [], first.manifest)
            self.assertNotIn(
                "source_snapshot_id",
                deltalake.DeltaTable(documents_uri).to_pyarrow_table().to_pylist()[0]["provenance"],
            )

            with_snapshot = dataclasses.replace(
                first.document,
                document_id="doc_01hx000000000000000000003x",
            )
            sink.persist(with_snapshot, [], first.manifest)

            rows = {
                row["document_id"]: row for row in deltalake.DeltaTable(documents_uri).to_pyarrow_table().to_pylist()
            }
            self.assertEqual(
                rows[with_snapshot.document_id]["provenance"]["source_snapshot_id"],
                SOURCE_SNAPSHOT_ID,
            )

    def test_a_new_section_metadata_key_survives_append_to_an_existing_table(self) -> None:
        """`published_sections` is cast to its own table schema too (#871).

        Every canonical surface goes through the same `_write_rows`, so proving the fix on
        `published_documents` alone would leave three tables asserted by nothing. Sections
        carry the section-level metadata the detail page renders, and the sections table is
        appended to on *every* publication, so it accumulates the drift fastest.
        """
        import deltalake

        with tempfile.TemporaryDirectory() as temp_dir:
            sections_uri = os.path.join(temp_dir, "published_sections")
            sink = DeltaCanonicalSink(
                DeltaSinkConfig(
                    published_documents_uri=os.path.join(temp_dir, "published_documents"),
                    published_sections_uri=sections_uri,
                    processing_manifests_uri=os.path.join(temp_dir, "processing_manifests"),
                )
            )

            first = build_processing_result()
            self.assertTrue(first.sections, "the fixture must produce at least one section")
            plain = [dataclasses.replace(section, metadata={"heading_level": 1}) for section in first.sections]
            sink.persist(first.document, plain, first.manifest)

            annotated = [
                dataclasses.replace(
                    section,
                    section_id=f"{section.section_id}_v2",
                    metadata={"heading_level": 1, "marginal_note": "Randtitel"},
                )
                for section in first.sections
            ]
            sink.persist(first.document, annotated, first.manifest)

            rows = {row["section_id"]: row for row in deltalake.DeltaTable(sections_uri).to_pyarrow_table().to_pylist()}
            self.assertEqual(rows[annotated[0].section_id]["metadata"]["marginal_note"], "Randtitel")

    def test_latest_document_revision_reads_back_published_history(self) -> None:
        # The read side of #652: the pipeline asks the sink what it already published so a
        # re-acquisition can be revision N+1 instead of another row pinned at 1.
        with tempfile.TemporaryDirectory() as temp_dir:
            sink = DeltaCanonicalSink(
                DeltaSinkConfig(
                    published_documents_uri=os.path.join(temp_dir, "published_documents"),
                    published_sections_uri=os.path.join(temp_dir, "published_sections"),
                    processing_manifests_uri=os.path.join(temp_dir, "processing_manifests"),
                )
            )

            # No table yet: nothing published anywhere, so the first publication starts at 1.
            self.assertIsNone(sink.latest_document_revision("doc_does_not_exist"))

            first = build_processing_result()
            sink.persist(first.document, first.sections, first.manifest)
            self.assertEqual(sink.latest_document_revision(first.document.document_id), 1)

            second = build_processing_result()
            sink.persist(
                dataclasses.replace(second.document, document_revision=2),
                second.sections,
                second.manifest,
            )
            self.assertEqual(sink.latest_document_revision(first.document.document_id), 2)

            # Scoped per document, not a global high-water mark.
            self.assertIsNone(sink.latest_document_revision("doc_other"))

    def test_latest_document_revision_degrades_to_none_when_surface_unreadable(self) -> None:
        # An unreadable surface must not fail the write path — a degraded read becoming a
        # dropped document is the worse outcome.
        sink = DeltaCanonicalSink(
            DeltaSinkConfig(
                published_documents_uri="/nonexistent/published_documents",
                published_sections_uri="/nonexistent/published_sections",
                processing_manifests_uri="/nonexistent/processing_manifests",
            )
        )

        self.assertIsNone(sink.latest_document_revision("doc_anything"))

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


def build_quarantined_processing_result(*, sink=None):
    """Run a valid, text-layer-free PDF through the pipeline (ADR-0047 `no_text_layer`)."""
    import io

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as reportlab_canvas

    buffer = io.BytesIO()
    canvas = reportlab_canvas.Canvas(buffer, pagesize=A4)
    canvas.rect(100, 400, 300, 200, stroke=1, fill=1)
    canvas.showPage()
    canvas.save()

    with tempfile.NamedTemporaryFile("wb", suffix=".pdf", delete=False) as pdf_handle:
        pdf_handle.write(buffer.getvalue())
        artifact_path = pdf_handle.name

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_handle:
        json.dump(
            build_manifest_payload(
                artifact_path,
                artifact_role="primary_document",
                content_type="application/pdf",
                parser_hints={
                    "expected_modalities": ["pdf"],
                    "expected_content_types": ["application/pdf"],
                    "preferred_primary_artifact_roles": ["primary_document"],
                    "ocr_expected": False,
                    "attachment_policy": "ignore",
                },
            ),
            manifest_handle,
        )
        manifest_path = manifest_handle.name

    try:
        pipeline = ProcessingPipeline(sink=sink, processing_version="di_2026_09_03")
        return pipeline.process_event(build_bundle_event(manifest_path))
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
