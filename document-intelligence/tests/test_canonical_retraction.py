"""Retracting a canonical row from Delta (issue #806, ADR-0057).

The blocked half of #806: the live index held two Bundesverfassung documents — a
pre-#652 duplicate — and *both* had canonical rows, so ``projection_reconcile`` saw no
orphan and re-acquisition minted a third id rather than converging. Removing the stale
canonical row had no tooling at all.

These tests pin the properties that make removing canonical truth survivable:

- a dry run mutates nothing (asserted against the real Delta table version, not a mock),
- the guardrails refuse an over-large retraction, an unbacked duplicate claim, and an
  empty canonical side,
- a targeted retraction removes exactly the intended document and leaves its sibling,
- the operation is idempotent, and
- the ledger is written *before* the delete, so a crash cannot lose provenance.
"""

import importlib.util
import os
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from document_intelligence.config.runtime import RuntimeSettings, SurfaceUris
from document_intelligence.errors import ProcessingError
from document_intelligence.jobs.canonical_retract import main, retractor_from_settings
from document_intelligence.persist.retraction import (
    RETRACTION_REASON_CODES,
    DeltaCanonicalRetractor,
    DocumentRetractionTarget,
    RetractionPlan,
    check_retraction_guardrails,
)

DELTA_AVAILABLE = importlib.util.find_spec("deltalake") is not None

# The two real ids from the #806 case shape: same document, two identity keys.
STALE_DOC = "doc_01jq7bdptzqv3xs0c41xpw1ybg"
SURVIVING_DOC = "doc_01jq7bdptzqv3xs0c41xpw1ybh"
THIRD_DOC = "doc_01jq7bdptzqv3xs0c41xpw1ybj"
PM_ID = "pm_01jq7bhgy7g0pkj4f1d03f8f8c"


def target(document_id: str, **overrides: Any) -> DocumentRetractionTarget:
    return DocumentRetractionTarget(
        document_id=document_id,
        document_rows=overrides.pop("document_rows", 1),
        section_rows=overrides.pop("section_rows", 3),
        revisions=overrides.pop("revisions", (1,)),
        titles=overrides.pop("titles", ("Bundesverfassung",)),
    )


def plan(**overrides: Any) -> RetractionPlan:
    base = RetractionPlan(
        targets=(target(STALE_DOC),),
        canonical_documents=100,
        reason_code="duplicate_identity",
        reason="pre-#652 ULID-keyed duplicate of the locator-keyed row",
        retracted_by="ops@evidara.example",
        superseded_by_document_id=SURVIVING_DOC,
        superseded_by_present=True,
    )
    return replace(base, **overrides)


class GuardrailTests(unittest.TestCase):
    """The guardrails are pure and need no Delta at all."""

    def test_accepts_a_small_well_formed_retraction(self) -> None:
        self.assertIsNone(check_retraction_guardrails(plan()))

    def test_refuses_an_empty_canonical_side(self) -> None:
        # The catastrophic misconfiguration: a wrong DI_SURFACES_ROOT_URI reads as
        # "canonical has nothing", and every guardrail expressed as a fraction of it
        # would divide by zero or pass trivially.
        refusal = check_retraction_guardrails(plan(canonical_documents=0))
        assert refusal is not None
        self.assertIn("enumerated 0 documents", refusal)

    def test_refuses_an_over_large_retraction(self) -> None:
        refusal = check_retraction_guardrails(
            plan(targets=(target(STALE_DOC), target(THIRD_DOC)), canonical_documents=10),
            max_retraction_fraction=0.1,
        )
        assert refusal is not None
        self.assertIn("2/10", refusal)
        self.assertIn("max-retraction-fraction", refusal)

    def test_allows_an_over_large_retraction_when_the_bound_is_raised_deliberately(self) -> None:
        self.assertIsNone(
            check_retraction_guardrails(
                plan(targets=(target(STALE_DOC), target(THIRD_DOC)), canonical_documents=10),
                max_retraction_fraction=1.0,
            )
        )

    def test_duplicate_identity_requires_a_survivor(self) -> None:
        refusal = check_retraction_guardrails(plan(superseded_by_document_id=None))
        assert refusal is not None
        self.assertIn("requires --superseded-by", refusal)

    def test_duplicate_identity_refuses_when_the_survivor_is_not_canonical(self) -> None:
        # Without this the operator deletes the corpus's only copy of the document.
        refusal = check_retraction_guardrails(plan(superseded_by_present=False))
        assert refusal is not None
        self.assertIn("only copy", refusal)

    def test_refuses_when_the_survivor_is_itself_being_retracted(self) -> None:
        refusal = check_retraction_guardrails(plan(targets=(target(STALE_DOC), target(SURVIVING_DOC))))
        assert refusal is not None
        self.assertIn("itself in the retraction set", refusal)

    def test_refuses_an_unknown_reason_code(self) -> None:
        refusal = check_retraction_guardrails(plan(reason_code="because"))
        assert refusal is not None
        self.assertIn("unknown --reason-code", refusal)

    def test_refuses_an_empty_reason(self) -> None:
        refusal = check_retraction_guardrails(plan(reason="   "))
        assert refusal is not None
        self.assertIn("--reason is required", refusal)

    def test_refuses_missing_operator_attribution(self) -> None:
        refusal = check_retraction_guardrails(plan(retracted_by=""))
        assert refusal is not None
        self.assertIn("--retracted-by is required", refusal)

    def test_a_target_canonical_does_not_have_is_not_a_refusal(self) -> None:
        # Idempotency: the second run of a completed retraction must succeed as a no-op.
        self.assertIsNone(
            check_retraction_guardrails(plan(targets=(target(STALE_DOC, document_rows=0, section_rows=0),)))
        )


class DocumentIdValidationTests(unittest.TestCase):
    def test_rejects_a_non_canonical_id_before_it_reaches_a_predicate(self) -> None:
        retractor = DeltaCanonicalRetractor("a", "b", "c", delta_module=object())
        with self.assertRaises(ProcessingError) as ctx:
            retractor.plan(
                ["doc_01jq7bdptzqv3xs0c41xpw1ybg' OR '1'='1"],
                reason_code="takedown",
                reason="x",
                retracted_by="ops",
            )
        self.assertEqual(ctx.exception.code, "retraction_invalid_document_id")


def _write(uri: str, rows: list[dict[str, Any]], mode: str = "append") -> None:
    import pyarrow as pa
    from deltalake import write_deltalake

    write_deltalake(uri, pa.Table.from_pylist(rows), mode=mode, schema_mode="merge")


def _document_row(document_id: str, revision: int = 1) -> dict[str, Any]:
    return {
        "document_id": document_id,
        "document_revision": revision,
        "processing_manifest_id": PM_ID,
        "title": "Bundesverfassung",
        "lifecycle_status": "active",
    }


def _section_rows(document_id: str, count: int = 3) -> list[dict[str, Any]]:
    return [
        {
            "section_id": f"sec_{document_id}_{ordinal}",
            "document_id": document_id,
            "document_revision": 1,
            # PUBLISHED_SECTIONS declares this non-nullable, and `get_full` filters
            # sections on the document row's manifest id. A fixture without it makes the
            # section read raise on a missing field — which `_get_sections` swallows into
            # an empty list, so the omission presents as "this document has no sections".
            "processing_manifest_id": PM_ID,
            "ordinal": ordinal,
            "content": "Art. 1",
        }
        for ordinal in range(count)
    ]


@unittest.skipUnless(DELTA_AVAILABLE, "deltalake is not installed")
class DeltaRetractionTests(unittest.TestCase):
    """Driven against real local Delta tables — a mock cannot prove a commit ordering."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.documents_uri = str(root / "published_documents")
        self.sections_uri = str(root / "published_sections")
        self.ledger_uri = str(root / "canonical_retractions")

        _write(self.documents_uri, [_document_row(STALE_DOC), _document_row(SURVIVING_DOC)], mode="overwrite")
        _write(
            self.sections_uri,
            [*_section_rows(STALE_DOC), *_section_rows(SURVIVING_DOC)],
            mode="overwrite",
        )

    def retractor(self) -> DeltaCanonicalRetractor:
        return DeltaCanonicalRetractor(self.documents_uri, self.sections_uri, self.ledger_uri)

    def document_ids(self) -> list[str]:
        from deltalake import DeltaTable

        return sorted(DeltaTable(self.documents_uri).to_pyarrow_table().column("document_id").to_pylist())

    def section_document_ids(self) -> list[str]:
        from deltalake import DeltaTable

        return sorted(DeltaTable(self.sections_uri).to_pyarrow_table().column("document_id").to_pylist())

    def ledger_rows(self) -> list[dict[str, Any]]:
        from deltalake import DeltaTable

        return DeltaTable(self.ledger_uri).to_pyarrow_table().to_pylist()

    def table_version(self, uri: str) -> int:
        from deltalake import DeltaTable

        return DeltaTable(uri).version()

    def build_plan(self, *document_ids: str) -> RetractionPlan:
        return self.retractor().plan(
            list(document_ids) or [STALE_DOC],
            reason_code="duplicate_identity",
            reason="pre-#652 ULID-keyed duplicate; the locator-keyed row survives",
            retracted_by="ops@evidara.example",
            superseded_by_document_id=SURVIVING_DOC,
        )

    def test_plan_resolves_rows_without_mutating_anything(self) -> None:
        version_before = self.table_version(self.documents_uri)
        sections_before = self.table_version(self.sections_uri)

        resolved = self.build_plan()

        self.assertEqual(resolved.canonical_documents, 2)
        self.assertTrue(resolved.superseded_by_present)
        [only] = resolved.found_targets
        self.assertEqual(only.document_id, STALE_DOC)
        self.assertEqual(only.document_rows, 1)
        self.assertEqual(only.section_rows, 3)
        self.assertEqual(only.revisions, (1,))

        # The dry run is the plan. Nothing moved: not the tables, not the ledger.
        self.assertEqual(self.table_version(self.documents_uri), version_before)
        self.assertEqual(self.table_version(self.sections_uri), sections_before)
        self.assertFalse(Path(self.ledger_uri).exists())
        self.assertEqual(self.document_ids(), sorted([STALE_DOC, SURVIVING_DOC]))

    def test_retraction_removes_exactly_the_target_and_leaves_the_sibling(self) -> None:
        summary = self.retractor().retract(self.build_plan())

        self.assertFalse(summary.failed)
        self.assertEqual(summary.retracted, 1)
        self.assertEqual(summary.retracted_document_ids, [STALE_DOC])
        self.assertEqual(self.document_ids(), [SURVIVING_DOC])
        # Sections go with the document; the sibling's sections are untouched.
        self.assertEqual(self.section_document_ids(), [SURVIVING_DOC] * 3)

    def test_retraction_records_provenance_in_the_ledger(self) -> None:
        summary = self.retractor().retract(self.build_plan())

        [record] = self.ledger_rows()
        self.assertEqual(record["document_id"], STALE_DOC)
        self.assertEqual(record["retracted_revisions"], [1])
        self.assertEqual(record["reason_code"], "duplicate_identity")
        self.assertEqual(record["superseded_by_document_id"], SURVIVING_DOC)
        self.assertEqual(record["retracted_by"], "ops@evidara.example")
        self.assertIn("#652", record["reason"])
        self.assertEqual(record["retraction_id"], summary.retraction_ids[0])

        surfaces = {entry["surface_name"]: entry for entry in record["surfaces"]}
        self.assertEqual(surfaces["published_documents"]["rows_matched"], 1)
        self.assertEqual(surfaces["published_sections"]["rows_matched"], 3)
        # `version_before` is the restore point; it must be the pre-delete version.
        self.assertEqual(surfaces["published_documents"]["version_before"], 0)

    def test_the_pre_retraction_version_is_still_readable_and_restorable(self) -> None:
        from deltalake import DeltaTable

        self.retractor().retract(self.build_plan())
        [record] = self.ledger_rows()
        restore_to = {entry["surface_name"]: entry["version_before"] for entry in record["surfaces"]}

        # No VACUUM is ever issued, so the retraction is undoable from the ledger alone.
        historic = DeltaTable(self.documents_uri, version=restore_to["published_documents"])
        self.assertIn(STALE_DOC, historic.to_pyarrow_table().column("document_id").to_pylist())

        DeltaTable(self.documents_uri).restore(restore_to["published_documents"])
        self.assertEqual(self.document_ids(), sorted([STALE_DOC, SURVIVING_DOC]))

    def test_retraction_is_idempotent(self) -> None:
        first = self.retractor().retract(self.build_plan())
        self.assertEqual(first.retracted, 1)

        # Re-plan against the now-smaller corpus and run again: a no-op, not an error.
        second_plan = self.retractor().plan(
            [STALE_DOC],
            reason_code="duplicate_identity",
            reason="pre-#652 ULID-keyed duplicate; the locator-keyed row survives",
            retracted_by="ops@evidara.example",
            superseded_by_document_id=SURVIVING_DOC,
        )
        self.assertIsNone(check_retraction_guardrails(second_plan))

        second = self.retractor().retract(second_plan)
        self.assertFalse(second.failed)
        self.assertEqual(second.retracted, 0)
        self.assertEqual(second.not_found_document_ids, [STALE_DOC])
        self.assertEqual(self.document_ids(), [SURVIVING_DOC])
        # A no-op writes no ledger row: the ledger records removals, not attempts.
        self.assertEqual(len(self.ledger_rows()), 1)

    def test_a_failed_ledger_append_deletes_nothing(self) -> None:
        # Ledger-before-delete is the whole ordering guarantee. Make the ledger
        # unwritable and assert canonical is untouched.
        retractor = DeltaCanonicalRetractor(
            self.documents_uri,
            self.sections_uri,
            self.ledger_uri,
        )
        resolved = self.build_plan()
        Path(self.ledger_uri).write_text("not a delta table", encoding="utf-8")

        summary = retractor.retract(resolved)

        self.assertTrue(summary.failed)
        assert summary.failure_reason is not None
        self.assertIn("ledger append failed", summary.failure_reason)
        self.assertEqual(self.document_ids(), sorted([STALE_DOC, SURVIVING_DOC]))
        self.assertEqual(len(self.section_document_ids()), 6)

    def test_guardrail_refuses_before_the_delete_when_the_survivor_is_missing(self) -> None:
        resolved = self.retractor().plan(
            [STALE_DOC],
            reason_code="duplicate_identity",
            reason="duplicate",
            retracted_by="ops",
            superseded_by_document_id=THIRD_DOC,  # never published
        )
        refusal = check_retraction_guardrails(resolved)
        assert refusal is not None
        self.assertIn("only copy", refusal)
        self.assertEqual(self.document_ids(), sorted([STALE_DOC, SURVIVING_DOC]))

    def test_retraction_never_stamps_a_legal_lifecycle_status(self) -> None:
        """A data-quality retraction must not touch the *legal* lifecycle axis.

        ``lifecycle_status`` is a claim about the norm (``active`` / ``superseded`` /
        ``repealed`` / ``withdrawn``). Stamping ``withdrawn`` on a row because the *record*
        was wrong would assert to every consumer that the law itself is no longer in force
        — for the #806 case, that Swiss constitutional law had been withdrawn. The
        surviving row's legal state has to come out of a retraction exactly as it went in.

        Guard-efficacy: mutate ``retract`` to write ``lifecycle_status='withdrawn'`` onto
        the survivor and this test goes red; without it that mutant survives the whole
        suite (mutation M10b).
        """
        from deltalake import DeltaTable

        before = {
            row["document_id"]: row["lifecycle_status"]
            for row in DeltaTable(self.documents_uri).to_pyarrow_table().to_pylist()
        }
        self.assertEqual(before[SURVIVING_DOC], "active")

        self.retractor().retract(self.build_plan())

        after = {
            row["document_id"]: row["lifecycle_status"]
            for row in DeltaTable(self.documents_uri).to_pyarrow_table().to_pylist()
        }
        # The stale row is gone outright — not tombstoned — and the survivor is untouched.
        self.assertEqual(after, {SURVIVING_DOC: "active"})
        # Nor does the ledger carry a lifecycle claim: it records a data-quality reason.
        [record] = self.ledger_rows()
        self.assertNotIn("lifecycle_status", record)
        self.assertIn(record["reason_code"], RETRACTION_REASON_CODES)

    def test_sections_are_deleted_before_the_document_row(self) -> None:
        """Sections first, so an interrupted run never serves a body with no provisions.

        A document row whose sections are already gone still answers a detail read — with
        an empty body. The reverse leaves an orphan section set, which no read path serves.

        Guard-efficacy: flip ``reversed(outcomes)`` to ``outcomes`` in ``retract`` and this
        test goes red; without it that mutant survives the whole suite (mutation M7).
        """
        retractor = self.retractor()
        order: list[str] = []
        original = retractor._delete_rows

        def recording(outcome: Any, document_id: str) -> None:
            order.append(outcome.surface_name)
            original(outcome, document_id)

        retractor._delete_rows = recording  # type: ignore[method-assign]
        retractor.retract(self.build_plan())

        self.assertEqual(order, ["published_sections", "published_documents"])

    def test_the_retractor_is_never_given_the_processing_manifests_surface(self) -> None:
        """``processing_manifests`` records that a run produced an output. It did.

        Deleting a manifest would falsify run history; the intended signal is a manifest
        whose ``published_document_ref`` no longer resolves. The retractor is structurally
        incapable of touching it — it is never handed the URI — and this test fails the
        moment someone wires one in.
        """
        settings = RuntimeSettings.from_environment(
            {"DI_SURFACES_ROOT_URI": "s3://bucket/surfaces"},
        )
        assert settings.surface_uris is not None
        manifests_uri = settings.surface_uris.processing_manifests_uri
        self.assertTrue(manifests_uri)

        retractor = retractor_from_settings(settings)
        wired = {value for key, value in vars(retractor).items() if key.endswith("_uri") and isinstance(value, str)}
        self.assertEqual(len(wired), 3)
        self.assertNotIn(manifests_uri, wired)


@unittest.skipUnless(DELTA_AVAILABLE, "deltalake is not installed")
class RetractedTableReadTests(unittest.TestCase):
    """Canonical reads must keep working once a surface has had rows deleted.

    delta-rs rewrites the surviving rows of a deleted file through a writer that
    materialises string columns as ``string_view``, while the dataset schema still reports
    ``string``. A bare ``pc.field(name) == python_str`` then raises
    ``ArrowNotImplementedError: Function 'equal' has no kernel matching input types``, and
    every ``document_id``-filtered read of that surface fails — not just the retracted row.

    **This class exists because the fixture in ``DeltaRetractionTests`` is too small to
    reach the condition.** Measured on deltalake 1.6.3 / pyarrow 25.0.1: a two-row table
    with one row deleted comes back as plain ``string`` and the defect does not reproduce,
    so the guard's own regression test passed with the guard reverted (mutation M2). Five
    rows reproduce it. A fixture calibrated below the threshold is an abstention, not a
    pass.
    """

    ROWS = 6

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.documents_uri = str(root / "published_documents")
        self.sections_uri = str(root / "published_sections")
        self.ledger_uri = str(root / "canonical_retractions")
        self.doc_ids = [STALE_DOC, SURVIVING_DOC] + [
            f"doc_01jq7bdptzqv3xs0c41xpw1y{suffix}" for suffix in "kmnpqr"[: self.ROWS - 2]
        ]
        _write(self.documents_uri, [_document_row(d) for d in self.doc_ids], mode="overwrite")
        _write(
            self.sections_uri,
            [row for d in self.doc_ids for row in _section_rows(d)],
            mode="overwrite",
        )

    def test_a_plain_pyarrow_equality_filter_would_have_broken_here(self) -> None:
        """The premise of the guard, asserted rather than assumed.

        If a future delta-rs / pyarrow pair stops producing ``string_view`` here, this test
        fails loudly and ``RetractedTableReadTests`` below becomes an abstention again —
        which is exactly what we want to be told, rather than discovering it as a green run
        over a condition that no longer exists.
        """
        import pyarrow.compute as pc
        from deltalake import DeltaTable

        DeltaTable(self.documents_uri).delete(predicate=f"document_id = '{STALE_DOC}'")
        dataset = DeltaTable(self.documents_uri).to_pyarrow_dataset()
        self.assertEqual(str(dataset.schema.field("document_id").type), "string")
        with self.assertRaises(Exception) as ctx:
            dataset.to_table(columns=["document_id"], filter=pc.field("document_id") == SURVIVING_DOC)
        self.assertIn("no kernel matching input types", str(ctx.exception))

    def test_canonical_reads_still_work_against_a_retracted_table(self) -> None:
        """Guard-efficacy: revert ``delta_string_equals`` to ``pc.field(n) == v`` and this
        goes red (mutation M2)."""
        from document_intelligence.persist.sinks import DeltaCanonicalSink, DeltaSinkConfig
        from document_intelligence.service.store import DeltaPublishedDocumentStore

        retractor = DeltaCanonicalRetractor(self.documents_uri, self.sections_uri, self.ledger_uri)
        retractor.retract(
            retractor.plan(
                [STALE_DOC],
                reason_code="duplicate_identity",
                reason="pre-#652 ULID-keyed duplicate; the locator-keyed row survives",
                retracted_by="ops@evidara.example",
                superseded_by_document_id=SURVIVING_DOC,
            )
        )

        store = DeltaPublishedDocumentStore(self.documents_uri, self.sections_uri, storage_options={})
        payload = store.get_full(SURVIVING_DOC, None)
        assert payload is not None
        self.assertEqual(payload["document_id"], SURVIVING_DOC)
        self.assertEqual(len(payload.get("sections", [])), 3)
        self.assertIsNone(store.get_full(STALE_DOC, None))

        # The append path reads history on every publication; it must survive too.
        sink = DeltaCanonicalSink(
            DeltaSinkConfig(self.documents_uri, self.sections_uri, "unused"),
            writer=lambda *args, **kwargs: None,
            storage_options={},
        )
        self.assertEqual(sink.latest_document_revision(SURVIVING_DOC), 1)

        # And so must the retractor's own resolution, which is how a resumed run converges.
        replanned = retractor.plan(
            [STALE_DOC],
            reason_code="duplicate_identity",
            reason="second pass",
            retracted_by="ops@evidara.example",
            superseded_by_document_id=SURVIVING_DOC,
        )
        self.assertEqual(replanned.missing_document_ids, (STALE_DOC,))
        self.assertEqual(replanned.canonical_documents, self.ROWS - 1)


@unittest.skipUnless(DELTA_AVAILABLE, "deltalake is not installed")
class CliTests(unittest.TestCase):
    """The CLI contract: dry-run by default, non-zero on refusal."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        _write(
            str(self.root / "published_documents"),
            [_document_row(STALE_DOC), _document_row(SURVIVING_DOC)],
            mode="overwrite",
        )
        _write(str(self.root / "published_sections"), _section_rows(STALE_DOC), mode="overwrite")

        previous = os.environ.get("DI_SURFACES_ROOT_URI")
        os.environ["DI_SURFACES_ROOT_URI"] = str(self.root)
        self.addCleanup(
            lambda: (
                os.environ.__setitem__("DI_SURFACES_ROOT_URI", previous)
                if previous is not None
                else os.environ.pop("DI_SURFACES_ROOT_URI", None)
            )
        )

    def document_ids(self) -> list[str]:
        from deltalake import DeltaTable

        return sorted(
            DeltaTable(str(self.root / "published_documents")).to_pyarrow_table().column("document_id").to_pylist()
        )

    def test_default_invocation_is_a_dry_run_that_mutates_nothing(self) -> None:
        exit_code = main(
            [
                STALE_DOC,
                "--reason-code",
                "duplicate_identity",
                "--reason",
                "pre-#652 duplicate",
                "--retracted-by",
                "ops",
                "--superseded-by",
                SURVIVING_DOC,
            ]
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(self.document_ids(), sorted([STALE_DOC, SURVIVING_DOC]))
        self.assertFalse((self.root / "canonical_retractions").exists())

    def test_retract_refuses_and_exits_non_zero_when_a_guardrail_trips(self) -> None:
        exit_code = main(
            [
                STALE_DOC,
                SURVIVING_DOC,
                "--reason-code",
                "erroneous_publication",
                "--reason",
                "both look wrong",
                "--retracted-by",
                "ops",
                "--retract",
                "--max-retraction-fraction",
                "0.5",
            ]
        )
        self.assertEqual(exit_code, 1)
        self.assertEqual(self.document_ids(), sorted([STALE_DOC, SURVIVING_DOC]))

    def test_default_bound_refuses_a_single_retraction_from_a_tiny_corpus(self) -> None:
        # The real #806 corpus was two documents, so retracting one is 50% of canonical
        # and the default 10% bound refuses it. That is the intended behaviour, and the
        # runbook tells the operator to raise the bound deliberately — pinned here so the
        # instruction cannot silently stop being true.
        exit_code = main(
            [
                STALE_DOC,
                "--reason-code",
                "duplicate_identity",
                "--reason",
                "pre-#652 duplicate",
                "--retracted-by",
                "ops",
                "--superseded-by",
                SURVIVING_DOC,
                "--retract",
            ]
        )
        self.assertEqual(exit_code, 1)
        self.assertEqual(self.document_ids(), sorted([STALE_DOC, SURVIVING_DOC]))

    def test_retract_removes_the_row_and_writes_the_ledger(self) -> None:
        exit_code = main(
            [
                STALE_DOC,
                "--reason-code",
                "duplicate_identity",
                "--reason",
                "pre-#652 duplicate",
                "--retracted-by",
                "ops",
                "--superseded-by",
                SURVIVING_DOC,
                "--retract",
                "--max-retraction-fraction",
                "1.0",
            ]
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(self.document_ids(), [SURVIVING_DOC])
        self.assertTrue((self.root / "canonical_retractions").exists())


class SettingsWiringTests(unittest.TestCase):
    def test_root_uri_derives_the_ledger_surface(self) -> None:
        uris = SurfaceUris.from_root_uri("s3://evidara-lakehouse/canonical")
        self.assertEqual(
            uris.canonical_retractions_uri,
            "s3://evidara-lakehouse/canonical/canonical_retractions",
        )

    def test_missing_surface_config_is_refused_rather_than_guessed(self) -> None:
        settings = RuntimeSettings.from_mapping({})
        with self.assertRaises(ProcessingError) as ctx:
            retractor_from_settings(settings)
        self.assertEqual(ctx.exception.code, "missing_surface_config")

    def test_explicit_per_surface_uris_without_a_ledger_are_refused(self) -> None:
        settings = RuntimeSettings.from_mapping(
            {
                "DI_PUBLISHED_DOCUMENTS_URI": "s3://x/published_documents",
                "DI_PUBLISHED_SECTIONS_URI": "s3://x/published_sections",
                "DI_PROCESSING_MANIFESTS_URI": "s3://x/processing_manifests",
            }
        )
        with self.assertRaises(ProcessingError) as ctx:
            retractor_from_settings(settings)
        self.assertEqual(ctx.exception.code, "missing_retraction_ledger_config")


if __name__ == "__main__":
    unittest.main()
