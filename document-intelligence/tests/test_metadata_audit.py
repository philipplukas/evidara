"""#871 step 2: the audit must tell *dropped* apart from *never emitted* — or say it cannot.

Every test here is written so that a plausible wrong implementation fails it:

* an audit that reports everything as lost fails
  ``test_a_declared_key_null_on_every_row_is_never_emitted``;
* an audit that reports everything as fine fails
  ``test_an_undeclared_key_with_a_witness_is_dropped``;
* an audit that guesses "never emitted" from absence — the guess this whole milestone exists
  to stop — fails ``test_an_undeclared_key_without_a_witness_is_indeterminate`` and
  ``test_a_witness_that_is_itself_undeclared_is_not_evidence``.
"""

import ast
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from document_intelligence.persist.metadata_audit import (  # noqa: E402
    EMITTED_KEYS,
    AuditReport,
    Status,
    audit_rows,
    plan_repair,
    render_text,
)

PIPELINE_SOURCE = os.path.join(os.path.dirname(__file__), "..", "src", "document_intelligence", "pipeline.py")

METADATA_STRUCT = frozenset(
    {
        "normalizer",
        "source_origin_kind",
        "trust_tier",
        "source_defaults",
        "extracted_metadata",
        "extraction_hints",
        "field_provenance",
        "official_citation",
        "in_force_from",
        "in_force_until",
        "regeste",
        "original_language",
        "translation_status",
        "source_flavor",
        "html_parse_used_fallback",
        "html_parse_recovery",
        "docling",
        "llm_extraction",
        "nlp",
        "commentary_insights",
    }
)
PROVENANCE_STRUCT = frozenset(
    {
        "tenant_id",
        "corpus_id",
        "scope_type",
        "source_id",
        "source_version_id",
        "run_id",
        "source_snapshot_id",
        "bundle_manifest_id",
        "artifact_id",
        "document_id",
        "document_revision",
        "processing_manifest_id",
    }
)


def _provenance(**overrides: object) -> dict[str, object]:
    row = {name: f"value_{name}" for name in PROVENANCE_STRUCT}
    row["document_revision"] = 1
    row.update(overrides)
    return row


def _finding(report: AuditReport, column: str, key: str):
    for candidate in report.findings:
        if candidate.column == column and candidate.key == key:
            return candidate
    raise AssertionError(f"no finding for {column}.{key}")


def _metadata_keys_assigned_in_pipeline() -> set[str]:
    """Re-derive, from the pipeline's own AST, every `metadata["..."] = ` key it writes."""

    with open(PIPELINE_SOURCE, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())

    keys: set[str] = set()
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for target in targets:
            if not isinstance(target, ast.Subscript):
                continue
            container = target.value
            name = None
            if isinstance(container, ast.Name):
                name = container.id
            elif isinstance(container, ast.Attribute):
                name = container.attr
            if name != "metadata":
                continue
            key = target.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                keys.add(key.value)
    return keys


class MetadataAuditRegistryTest(unittest.TestCase):
    def test_the_registry_covers_every_metadata_key_the_pipeline_assigns(self) -> None:
        """A key added to `_build_document` and not to `EMITTED_KEYS` is a key the audit
        cannot see — which is the same silence #871 is about, one layer up. This scan is the
        drift guard: it re-derives the keys from `pipeline.py` and fails when one is
        unregistered.
        """

        scanned = _metadata_keys_assigned_in_pipeline()

        # Non-vacuity: a scanner that matched nothing would pass the subset assertion below
        # unconditionally. Pin the shape of what it must find first.
        self.assertGreaterEqual(len(scanned), 10, f"the AST scan found too little to be trusted: {scanned}")
        for sentinel in ("official_citation", "regeste", "docling", "field_provenance"):
            self.assertIn(sentinel, scanned, "the AST scan stopped seeing pipeline metadata assignments")

        registered = {spec.key for spec in EMITTED_KEYS if spec.column == "metadata"}
        self.assertEqual(
            set(),
            scanned - registered,
            "pipeline.py writes metadata keys the audit registry does not know about",
        )


class MetadataAuditVerdictTest(unittest.TestCase):
    def _report(self, *, metadata_struct=METADATA_STRUCT, rows=None, provenance_struct=PROVENANCE_STRUCT):
        return audit_rows(
            declared_fields={"metadata": metadata_struct, "provenance": provenance_struct},
            rows=rows if rows is not None else [],
            table_uri="memory://test",
        )

    def test_an_undeclared_key_with_a_witness_is_dropped(self) -> None:
        """The table cannot hold `in_force_from`, and `field_provenance.in_force_from` on the
        same row proves the pipeline resolved one. That is a drop, not an absence.
        """

        rows = [
            {
                "document_id": "doc_1",
                "provenance": _provenance(),
                "metadata": {
                    "source_origin_kind": "official",
                    "trust_tier": "tier_1",
                    "field_provenance": {"in_force_from": {"value": "2020-01-01", "source": "manifest"}},
                },
            }
        ]
        report = self._report(metadata_struct=METADATA_STRUCT - {"in_force_from"}, rows=rows)
        finding = _finding(report, "metadata", "in_force_from")
        self.assertEqual(Status.DROPPED, finding.status)
        self.assertEqual(1, finding.rows_witness_without_value)
        self.assertIn("field_provenance.in_force_from", finding.witnesses_available)

    def test_an_undeclared_key_without_a_witness_is_indeterminate(self) -> None:
        """Same table, same missing key — but no row shows the pipeline ever resolved one.

        The honest answer is "cannot tell", and an audit that answers `never_emitted` here is
        asserting an absence it has not established. `regeste` is a real example: a statute
        legitimately has none.
        """

        rows = [
            {
                "document_id": "doc_1",
                "provenance": _provenance(),
                "metadata": {
                    "source_origin_kind": "official",
                    "trust_tier": "tier_1",
                    "extracted_metadata": {"court_name": "BGer"},
                },
            }
        ]
        report = self._report(metadata_struct=METADATA_STRUCT - {"regeste"}, rows=rows)
        finding = _finding(report, "metadata", "regeste")
        self.assertEqual(Status.INDETERMINATE, finding.status)
        self.assertEqual(0, finding.rows_witness_without_value)
        self.assertIn("extracted_metadata.headnote", finding.witnesses_available)

    def test_a_declared_key_null_on_every_row_is_never_emitted(self) -> None:
        """The other half of the distinction, and the only case where absence *is* evidence.

        The struct declares `regeste`, so the append cast preserved whatever each batch
        carried. Null on every row therefore means nothing upstream produced one — which is a
        corpus fact, not a defect, and must not be reported as loss.
        """

        rows = [
            {
                "document_id": "doc_1",
                "provenance": _provenance(),
                "metadata": {"source_origin_kind": "official", "trust_tier": "tier_1", "regeste": None},
            }
        ]
        report = self._report(rows=rows)
        self.assertEqual(Status.NEVER_EMITTED, _finding(report, "metadata", "regeste").status)

    def test_a_witness_that_is_itself_undeclared_is_not_evidence(self) -> None:
        """`field_provenance` is a struct too, so it is exposed to the same drop.

        When the witness is missing from the schema, its silence says nothing — it may have
        been dropped by the very mechanism under audit. The finding must stay INDETERMINATE
        and name the unusable witness, rather than read an empty witness as "never emitted".
        """

        narrow = METADATA_STRUCT - {"in_force_from", "field_provenance", "extraction_hints", "extracted_metadata"}
        rows = [
            {
                "document_id": "doc_1",
                "provenance": _provenance(),
                "metadata": {"source_origin_kind": "official", "trust_tier": "tier_1"},
            }
        ]
        report = self._report(metadata_struct=narrow, rows=rows)
        finding = _finding(report, "metadata", "in_force_from")
        self.assertEqual(Status.INDETERMINATE, finding.status)
        self.assertEqual((), finding.witnesses_available)
        self.assertIn("field_provenance.in_force_from", finding.witnesses_unavailable)
        self.assertIn("themselves suspect", finding.reason)

    def test_an_unconditionally_emitted_key_needs_no_witness(self) -> None:
        """`provenance.run_id` is required by `Provenance.from_dict` and non-null on every
        canonical row. Undeclared, it is provably dropped — no witness required, and reporting
        it as INDETERMINATE would be under-claiming a certainty.
        """

        rows = [{"document_id": "doc_1", "provenance": _provenance(), "metadata": {"trust_tier": "tier_1"}}]
        report = self._report(rows=rows, provenance_struct=PROVENANCE_STRUCT - {"run_id"})
        self.assertEqual(Status.DROPPED, _finding(report, "provenance", "run_id").status)

    def test_a_key_dropped_only_on_some_rows_is_still_dropped(self) -> None:
        """A declared key populated on one row and null on another that carries a witness is a
        per-row loss. An audit that stops at "declared and non-empty" calls this table clean.
        """

        rows = [
            {
                "document_id": "doc_good",
                "provenance": _provenance(),
                "metadata": {
                    "source_origin_kind": "official",
                    "trust_tier": "tier_1",
                    "official_citation": "BGBl. II Nr. 219/2026",
                    "extracted_metadata": {"publication_organ": "BGBl. II Nr. 219/2026"},
                },
            },
            {
                "document_id": "doc_lost",
                "provenance": _provenance(),
                "metadata": {
                    "source_origin_kind": "official",
                    "trust_tier": "tier_1",
                    "official_citation": None,
                    "extracted_metadata": {"publication_organ": "BGBl. II Nr. 100/2026"},
                },
            },
        ]
        report = self._report(rows=rows)
        finding = _finding(report, "metadata", "official_citation")
        self.assertEqual(Status.DROPPED, finding.status)
        self.assertEqual(1, finding.rows_witness_without_value)
        self.assertEqual(1, finding.rows_with_value)

    def test_a_blank_witness_does_not_fire(self) -> None:
        """Every route a witness stands for guards on a non-blank string, so an empty
        `publication_organ` is a value the pipeline itself ignores. Firing on it would report a
        drop that never happened.
        """

        rows = [
            {
                "document_id": "doc_1",
                "provenance": _provenance(),
                "metadata": {
                    "source_origin_kind": "official",
                    "trust_tier": "tier_1",
                    "official_citation": None,
                    "extracted_metadata": {"publication_organ": "   "},
                },
            }
        ]
        report = self._report(rows=rows)
        self.assertEqual(Status.NEVER_EMITTED, _finding(report, "metadata", "official_citation").status)

    def test_an_empty_table_supports_no_conclusion(self) -> None:
        """Zero rows is zero evidence — including for the unconditional keys, whose certainty
        comes from the rows existing at all.
        """

        report = self._report(metadata_struct=METADATA_STRUCT - {"regeste"}, rows=[])
        self.assertEqual(
            {Status.INDETERMINATE},
            {finding.status for finding in report.findings},
        )

    def test_a_column_that_is_absent_or_not_a_struct_yields_no_claim(self) -> None:
        """`published_commentary_insights` declares `metadata` as `map<string,string>`, which
        cannot drop keys. Auditing it as if it were a struct would invent findings.
        """

        report = audit_rows(
            declared_fields={"metadata": None, "provenance": PROVENANCE_STRUCT},
            rows=[{"document_id": "doc_1", "provenance": _provenance(), "metadata": {"a": "b"}}],
        )
        self.assertEqual(("metadata",), report.undeclared_columns)
        self.assertEqual(Status.INDETERMINATE, _finding(report, "metadata", "regeste").status)
        self.assertEqual(Status.PRESENT, _finding(report, "provenance", "run_id").status)

    def test_declared_fields_the_pipeline_does_not_write_are_reported(self) -> None:
        rows = [{"document_id": "doc_1", "provenance": _provenance(), "metadata": {"trust_tier": "t"}}]
        report = self._report(metadata_struct=METADATA_STRUCT | {"legacy_key"}, rows=rows)
        self.assertIn("metadata.legacy_key", report.unregistered_declared_fields)

    def test_render_text_names_the_dropped_keys(self) -> None:
        rows = [
            {
                "document_id": "doc_1",
                "provenance": _provenance(),
                "metadata": {
                    "source_origin_kind": "official",
                    "trust_tier": "tier_1",
                    "field_provenance": {"in_force_until": {"value": "2021-01-01", "source": "manifest"}},
                },
            }
        ]
        report = self._report(metadata_struct=METADATA_STRUCT - {"in_force_until"}, rows=rows)
        rendered = render_text(report)
        self.assertIn("DROPPED", rendered)
        self.assertIn("metadata.in_force_until", rendered)


class RepairPlanTest(unittest.TestCase):
    def _dropped_report(self, rows):
        return audit_rows(
            declared_fields={"metadata": METADATA_STRUCT - {"in_force_from"}, "provenance": PROVENANCE_STRUCT},
            rows=rows,
            table_uri="memory://test",
        )

    def _row(self, document_id: str, **provenance_overrides: object) -> dict[str, object]:
        return {
            "document_id": document_id,
            "provenance": _provenance(**provenance_overrides),
            "metadata": {
                "source_origin_kind": "official",
                "trust_tier": "tier_1",
                "field_provenance": {"in_force_from": {"value": "2020-01-01", "source": "manifest"}},
            },
        }

    def test_a_row_with_a_bundle_is_reprocessed_and_one_without_is_re_acquired(self) -> None:
        """The repair plan's own input is exposed to the defect it is repairing: the bundle to
        reprocess is read from `provenance`, a struct column. A row that lost
        `bundle_manifest_id` is not repairable from anything the platform holds, and must be
        reported as such rather than quietly dropped from the plan.
        """

        rows = [self._row("doc_have_bundle"), self._row("doc_no_bundle", bundle_manifest_id=None)]
        plan = plan_repair(self._dropped_report(rows), rows)
        self.assertEqual(("metadata.in_force_from",), tuple(k for k in plan.dropped_keys if "in_force" in k))
        self.assertEqual(["doc_have_bundle"], [item["document_id"] for item in plan.reprocess])
        self.assertEqual(("doc_no_bundle",), plan.reacquire)
        self.assertTrue(any("PRECONDITION" in note for note in plan.notes))
        self.assertTrue(any("re-acquired from the authority" in note for note in plan.notes))

    def test_a_clean_table_plans_no_work(self) -> None:
        rows = [
            {
                "document_id": "doc_1",
                "provenance": _provenance(),
                "metadata": {
                    "source_origin_kind": "official",
                    "trust_tier": "tier_1",
                    "in_force_from": "2020-01-01",
                    "field_provenance": {"in_force_from": {"value": "2020-01-01", "source": "manifest"}},
                },
            }
        ]
        report = audit_rows(
            declared_fields={"metadata": METADATA_STRUCT, "provenance": PROVENANCE_STRUCT},
            rows=rows,
        )
        plan = plan_repair(report, rows)
        self.assertEqual((), plan.dropped_keys)
        self.assertEqual((), plan.reprocess)
        self.assertTrue(any("would change nothing" in note for note in plan.notes))


class DeltaTableAuditTest(unittest.TestCase):
    """The adapter half: read a real Delta table's struct schema, not a hand-built dict."""

    def test_a_narrow_delta_table_is_audited_as_dropped(self) -> None:
        """Reproduces the deployed shape — a table whose first (and only) batch lacked
        `in_force_from` while carrying the witness that proves the pipeline resolved one — and
        audits it through `deltalake` end to end.
        """

        import deltalake
        import pyarrow as pa

        from document_intelligence.persist.metadata_audit import audit_delta_table

        rows = [
            {
                "document_id": "doc_1",
                "provenance": _provenance(),
                "metadata": {
                    "source_origin_kind": "official",
                    "trust_tier": "tier_1",
                    "regeste": None,
                    "field_provenance": {"in_force_from": {"value": "2020-01-01", "source": "manifest"}},
                },
            }
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            uri = os.path.join(temp_dir, "published_documents")
            deltalake.write_deltalake(uri, pa.Table.from_pylist(rows), mode="overwrite")
            report = audit_delta_table(uri)

        self.assertEqual(1, report.rows_total)
        self.assertEqual(Status.DROPPED, _finding(report, "metadata", "in_force_from").status)
        # Declared and null: the table kept what the batch carried, so this one is upstream truth.
        self.assertEqual(Status.NEVER_EMITTED, _finding(report, "metadata", "regeste").status)
        self.assertEqual(Status.PRESENT, _finding(report, "provenance", "run_id").status)


SECTIONIZE_SOURCE = os.path.join(
    os.path.dirname(__file__), "..", "src", "document_intelligence", "sectionize", "html.py"
)
NORMALIZE_DIR = os.path.join(os.path.dirname(__file__), "..", "src", "document_intelligence", "normalize")


def _section_metadata_keys_from_source() -> set[str]:
    """Re-derive every key a section row's `metadata` can carry, from the producers' AST.

    Two producers, because a section's metadata is `{"heading_level", "block_id",
    **block.attrs}` (`sectionize/html.py:34-36`): the sectionizer's own keys, and every
    `Block(attrs=...)` literal in the normalizers — which is where the loss actually varies,
    since each normalizer emits a different set.
    """

    keys: set[str] = set()

    with open(SECTIONIZE_SOURCE, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    for node in ast.walk(tree):
        # `metadata: dict[str, Any] = {"heading_level": ..., "block_id": ...}`
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = list(node.targets) if isinstance(node, ast.Assign) else [node.target]
            names = {t.id for t in targets if isinstance(t, ast.Name)}
            if "metadata" in names and isinstance(node.value, ast.Dict):
                for key in node.value.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        keys.add(key.value)
            # `metadata["parent_title"] = ...`
            for target in targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "metadata"
                    and isinstance(target.slice, ast.Constant)
                    and isinstance(target.slice.value, str)
                ):
                    keys.add(target.slice.value)

    for entry in sorted(os.listdir(NORMALIZE_DIR)):
        if not entry.endswith(".py"):
            continue
        with open(os.path.join(NORMALIZE_DIR, entry), encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        for node in ast.walk(tree):
            # `Block(..., attrs={"tag": ..., "page_no": ...})`
            if isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if keyword.arg == "attrs" and isinstance(keyword.value, ast.Dict):
                        for key in keyword.value.keys:
                            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                                keys.add(key.value)
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = list(node.targets) if isinstance(node, ast.Assign) else [node.target]
                # `attrs: dict[str, Any] = {"tag": "pdf", "page_no": ..., "bbox_top": ...}`
                if any(isinstance(t, ast.Name) and t.id == "attrs" for t in targets) and isinstance(
                    node.value, ast.Dict
                ):
                    for key in node.value.keys:
                        if isinstance(key, ast.Constant) and isinstance(key.value, str):
                            keys.add(key.value)
                # `attrs["anchor"] = ...`
                for target in targets:
                    if (
                        isinstance(target, ast.Subscript)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "attrs"
                        and isinstance(target.slice, ast.Constant)
                        and isinstance(target.slice.value, str)
                    ):
                        keys.add(target.slice.value)

    # The third producer: the pipeline adds its own keys to a section's metadata
    # (`section_metadata["citations"] = ...`, pipeline.py:981).
    with open(PIPELINE_SOURCE, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id == "section_metadata"
                and isinstance(target.slice, ast.Constant)
                and isinstance(target.slice.value, str)
            ):
                keys.add(target.slice.value)
    return keys


class SurfaceRegistryTest(unittest.TestCase):
    """#871 step 2: a registry is a claim about one surface's producer, not about tables.

    Measured against production on 2026-09-19, auditing `published_sections` with the
    document registry reported `metadata.source_origin_kind` and `metadata.trust_tier` as
    lost on all 57,128 rows — citing `pipeline.py:721`, which is in `_build_document` and
    never touches a section row — while registering none of the eleven keys those rows
    actually carry. Wrong in both directions at once, from one default argument.
    """

    def test_the_section_registry_covers_every_key_a_section_row_can_carry(self) -> None:
        from document_intelligence.persist.metadata_audit import SECTION_EMITTED_KEYS

        scanned = _section_metadata_keys_from_source()

        # Non-vacuity first: a scanner that matched nothing passes the subset check below
        # unconditionally, which is how a drift guard becomes decoration.
        self.assertGreaterEqual(len(scanned), 10, f"the AST scan found too little to be trusted: {scanned}")
        sentinels = ("heading_level", "block_id", "page_no", "bbox_top", "official_label", "parent_title", "citations")
        for sentinel in sentinels:
            self.assertIn(sentinel, scanned, "the AST scan stopped seeing section metadata producers")

        registered = {spec.key for spec in SECTION_EMITTED_KEYS if spec.column == "metadata"}
        self.assertEqual(
            set(),
            scanned - registered,
            "a section producer writes metadata keys the audit registry does not know about",
        )

    def test_no_section_key_is_unconditional(self) -> None:
        """`sectionize/html.py:63-73` emits `metadata={}` for a whole-body fallback section.

        So there is no key a section row must carry, and marking one unconditional would
        reproduce the false loss this registry exists to stop — that is exactly how the
        document registry produced two on 57,128 section rows.
        """
        from document_intelligence.persist.metadata_audit import SECTION_EMITTED_KEYS

        unconditional = [spec.key for spec in SECTION_EMITTED_KEYS if spec.column == "metadata" and spec.unconditional]
        self.assertEqual([], unconditional)

    def test_a_section_table_is_not_audited_against_the_document_registry(self) -> None:
        import deltalake
        import pyarrow as pa

        from document_intelligence.persist.metadata_audit import audit_delta_table

        rows = [
            {
                "section_id": "sec_1",
                "document_id": "doc_1",
                "provenance": _provenance(),
                "metadata": {"heading_level": 1, "block_id": "blk_0001", "tag": "pdf"},
            }
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            uri = os.path.join(temp_dir, "published_sections")
            deltalake.write_deltalake(uri, pa.Table.from_pylist(rows), mode="overwrite")
            report = audit_delta_table(uri)

        self.assertEqual("published_sections", report.surface)
        audited = {(f.column, f.key) for f in report.findings}
        # The document-only keys are not claims this surface can support at all.
        self.assertNotIn(("metadata", "source_origin_kind"), audited)
        self.assertNotIn(("metadata", "trust_tier"), audited)
        self.assertEqual((), report.dropped)
        # ...and the keys sections do carry are now audited, which the document registry
        # never did: it called all eleven of them "declared but unknown to this pipeline".
        self.assertIn(("metadata", "page_no"), audited)
        self.assertEqual(Status.PRESENT, _finding(report, "metadata", "heading_level").status)

    def test_a_section_key_the_table_dropped_is_still_seen(self) -> None:
        """The other half: scoping the registry must not cost the ability to find a real loss.

        A PDF block always sets `page_no` and `bbox_top` in one literal
        (`normalize/pdf.py:282`), so a row carrying one without the other is a drop.
        """
        import deltalake
        import pyarrow as pa

        from document_intelligence.persist.metadata_audit import audit_delta_table

        rows = [
            {
                "section_id": "sec_1",
                "document_id": "doc_1",
                "provenance": _provenance(),
                "metadata": {"block_id": "blk_0001", "tag": "pdf", "bbox_top": 12.5},
            }
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            uri = os.path.join(temp_dir, "published_sections")
            deltalake.write_deltalake(uri, pa.Table.from_pylist(rows), mode="overwrite")
            report = audit_delta_table(uri)

        finding = _finding(report, "metadata", "page_no")
        self.assertEqual(Status.DROPPED, finding.status)
        self.assertIn("bbox_top", finding.reason)

    def test_an_unknown_surface_is_refused_rather_than_guessed(self) -> None:
        import deltalake
        import pyarrow as pa

        from document_intelligence.persist.metadata_audit import UnknownSurfaceError, audit_delta_table

        rows = [{"document_id": "doc_1", "provenance": _provenance(), "metadata": {"normalizer": "pdf_v1"}}]
        with tempfile.TemporaryDirectory() as temp_dir:
            uri = os.path.join(temp_dir, "published_something_new")
            deltalake.write_deltalake(uri, pa.Table.from_pylist(rows), mode="overwrite")
            with self.assertRaises(UnknownSurfaceError) as raised:
                audit_delta_table(uri)

        self.assertIn("published_something_new", str(raised.exception))
        self.assertIn("published_documents", str(raised.exception))

    def test_an_explicit_surface_overrides_the_uri(self) -> None:
        from document_intelligence.persist.metadata_audit import SECTION_EMITTED_KEYS, registry_for_surface

        self.assertIs(SECTION_EMITTED_KEYS, registry_for_surface("published_sections"))

    def test_a_surface_with_no_audited_struct_columns_makes_no_claim(self) -> None:
        """`canonical_retractions` (ADR-0057) carries neither struct column.

        Auditing it against the document registry produced 32 "nothing can be established"
        findings — noise that reads like a report.
        """
        from document_intelligence.persist.metadata_audit import registry_for_surface

        self.assertEqual((), registry_for_surface("canonical_retractions"))


if __name__ == "__main__":
    unittest.main()
