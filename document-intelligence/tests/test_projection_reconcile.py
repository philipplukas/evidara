"""Reconciling projection: index minus canonical (issue #652, ADR-0005).

The backfill can only add — it upserts on ``document_id`` — so an indexed document whose
canonical row is gone survives every rebuild and stays user-visible. These tests pin the
half that removes it, and in particular the guardrails: the dangerous failure of this job
is not one wrong deletion but a canonical side that reads as empty, making the entire
index look orphaned.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from document_intelligence.errors import ProcessingError
from document_intelligence.events.document_withdrawn import (
    build_document_withdrawn_event_from_indexed_row,
)
from document_intelligence.jobs.projection_bridge_consumer import PermanentForwardError
from document_intelligence.jobs.projection_reconcile import (
    ReconcileSummary,
    check_delete_guardrails,
    iter_indexed_documents,
    reconcile_documents,
)
from document_intelligence.validate.schema_validation import validate_instance_against_contract
from support import RUN_ID, SOURCE_ID, SOURCE_VERSION_ID

CANONICAL_DOC = "doc_01jq7bdptzqv3xs0c41xpw1ybg"
ORPHAN_DOC = "doc_01jq7bdptzqv3xs0c41xpw1ybh"
ORPHAN_DOC_2 = "doc_01jq7bdptzqv3xs0c41xpw1ybj"
PM_ID = "pm_01jq7bhgy7g0pkj4f1d03f8f8c"


def indexed_row(document_id: str, **overrides: Any) -> dict[str, Any]:
    """A row shaped like `GET /v1/projections/documents` returns."""
    row: dict[str, Any] = {
        "document_id": document_id,
        "document_revision": 1,
        "processing_manifest_id": PM_ID,
        "source_id": SOURCE_ID,
        "source_version_id": SOURCE_VERSION_ID,
        "run_id": RUN_ID,
        "title": "Bundesverfassung",
    }
    row.update(overrides)
    return row


class DocumentWithdrawnFromIndexedRowTest(unittest.TestCase):
    def test_builds_a_contract_valid_withdrawn_event(self) -> None:
        event = build_document_withdrawn_event_from_indexed_row(
            indexed_row(ORPHAN_DOC),
            reason_summary="reconcile: no canonical row",
        )

        validate_instance_against_contract(event, "events/document-withdrawn.schema.json")
        self.assertEqual(event["payload"]["document_id"], ORPHAN_DOC)
        # `remove`, never `hide`: an orphan has no canonical row to stay auditable against.
        self.assertEqual(event["payload"]["search_disposition"], "remove")
        # Provenance ids come off the index row, not from thin air.
        self.assertEqual(event["payload"]["provenance"]["run_id"], RUN_ID)

    def test_each_emission_carries_a_fresh_event_id(self) -> None:
        # A surviving projection-history index must not short-circuit a re-run as a duplicate.
        first = build_document_withdrawn_event_from_indexed_row(indexed_row(ORPHAN_DOC), reason_summary="x")
        second = build_document_withdrawn_event_from_indexed_row(indexed_row(ORPHAN_DOC), reason_summary="x")
        self.assertNotEqual(first["event_id"], second["event_id"])

    def test_refuses_a_row_without_usable_provenance(self) -> None:
        for missing in ("processing_manifest_id", "source_id", "source_version_id", "run_id"):
            with self.subTest(missing=missing):
                row = indexed_row(ORPHAN_DOC, **{missing: None})
                with self.assertRaises(ProcessingError) as ctx:
                    build_document_withdrawn_event_from_indexed_row(row, reason_summary="x")
                self.assertEqual(ctx.exception.code, "reconcile_row_unwithdrawable")

    def test_refuses_a_row_without_a_document_revision(self) -> None:
        with self.assertRaises(ProcessingError):
            build_document_withdrawn_event_from_indexed_row(
                indexed_row(ORPHAN_DOC, document_revision=None), reason_summary="x"
            )


class ReconcileDocumentsTest(unittest.TestCase):
    def test_dry_run_reports_orphans_and_posts_nothing(self) -> None:
        posted: list[dict[str, Any]] = []

        summary = reconcile_documents(
            [indexed_row(CANONICAL_DOC), indexed_row(ORPHAN_DOC)],
            {CANONICAL_DOC},
            post=posted.append,
        )

        self.assertTrue(summary.dry_run)
        self.assertEqual(summary.indexed_scanned, 2)
        self.assertEqual(summary.orphaned, 1)
        self.assertEqual(summary.deleted, 0)
        self.assertEqual(summary.orphan_document_ids, [ORPHAN_DOC])
        self.assertEqual(posted, [])

    def test_withdraws_only_documents_canonical_does_not_back(self) -> None:
        posted: list[dict[str, Any]] = []
        deleted: list[str] = []

        summary = reconcile_documents(
            [indexed_row(CANONICAL_DOC), indexed_row(ORPHAN_DOC)],
            {CANONICAL_DOC},
            post=posted.append,
            on_deleted=deleted.append,
            delete_orphans=True,
        )

        self.assertEqual(summary.deleted, 1)
        self.assertEqual(deleted, [ORPHAN_DOC])
        self.assertEqual([e["payload"]["document_id"] for e in posted], [ORPHAN_DOC])
        self.assertEqual([e["event_type"] for e in posted], ["document.withdrawn"])

    def test_reports_an_orphan_it_cannot_withdraw_instead_of_inventing_ids(self) -> None:
        posted: list[dict[str, Any]] = []

        summary = reconcile_documents(
            [indexed_row(ORPHAN_DOC, run_id=None)],
            {CANONICAL_DOC},
            post=posted.append,
            delete_orphans=True,
        )

        self.assertEqual(summary.orphaned, 1)
        self.assertEqual(summary.deleted, 0)
        self.assertEqual(summary.skipped_unwithdrawable, 1)
        self.assertEqual(summary.unwithdrawable_document_ids, [ORPHAN_DOC])
        self.assertEqual(posted, [])

    def test_a_rejected_withdrawal_does_not_strand_the_rest_of_the_diff(self) -> None:
        posted: list[dict[str, Any]] = []

        def post(event: dict[str, Any]) -> None:
            if event["payload"]["document_id"] == ORPHAN_DOC:
                raise PermanentForwardError("400 rejected")
            posted.append(event)

        summary = reconcile_documents(
            [indexed_row(ORPHAN_DOC), indexed_row(ORPHAN_DOC_2)],
            set(),
            post=post,
            delete_orphans=True,
        )

        self.assertEqual(summary.rejected, 1)
        self.assertEqual(summary.deleted, 1)
        self.assertEqual([e["payload"]["document_id"] for e in posted], [ORPHAN_DOC_2])

    def test_retries_a_transient_failure_then_fails_the_run(self) -> None:
        attempts: list[int] = []

        def post(_event: dict[str, Any]) -> None:
            attempts.append(1)
            raise RuntimeError("503")

        summary = reconcile_documents(
            [indexed_row(ORPHAN_DOC)],
            set(),
            post=post,
            delete_orphans=True,
            max_retries=2,
            sleep=lambda _seconds: None,
        )

        self.assertEqual(len(attempts), 3)  # initial + 2 retries
        self.assertTrue(summary.failed)
        self.assertEqual(summary.deleted, 0)


class DeleteGuardrailsTest(unittest.TestCase):
    def test_refuses_when_canonical_enumerated_nothing(self) -> None:
        # The single most dangerous misconfiguration: a wrong DI_SURFACES_ROOT_URI makes
        # every indexed document look orphaned.
        summary = ReconcileSummary(indexed_scanned=24, canonical_documents=0, orphaned=24)

        refusal = check_delete_guardrails(summary, max_orphan_fraction=1.0)

        self.assertIsNotNone(refusal)
        assert refusal is not None
        self.assertIn("0 documents", refusal)

    def test_refuses_when_the_orphan_share_exceeds_the_bound(self) -> None:
        summary = ReconcileSummary(indexed_scanned=24, canonical_documents=2, orphaned=22)

        self.assertIsNotNone(check_delete_guardrails(summary, max_orphan_fraction=0.25))

    def test_allows_the_same_diff_when_the_operator_raises_the_bound(self) -> None:
        summary = ReconcileSummary(indexed_scanned=24, canonical_documents=2, orphaned=22)

        self.assertIsNone(check_delete_guardrails(summary, max_orphan_fraction=1.0))

    def test_allows_a_small_diff(self) -> None:
        summary = ReconcileSummary(indexed_scanned=100, canonical_documents=99, orphaned=1)

        self.assertIsNone(check_delete_guardrails(summary, max_orphan_fraction=0.25))


class IterIndexedDocumentsTest(unittest.TestCase):
    def test_follows_the_cursor_across_pages(self) -> None:
        pages = {
            None: {"data": [{"document_id": "doc_a"}], "next_after": "doc_a", "limit": 1},
            "doc_a": {"data": [{"document_id": "doc_b"}], "limit": 1},
        }
        requested: list[str] = []

        def fetch(url: str) -> dict[str, Any]:
            requested.append(url)
            after = None
            if "after=" in url:
                after = url.split("after=")[1].split("&")[0]
            return pages[after]

        rows = list(iter_indexed_documents("http://ls", page_size=1, fetch_page=fetch))

        self.assertEqual([r["document_id"] for r in rows], ["doc_a", "doc_b"])
        self.assertIn("/v1/projections/documents?limit=1", requested[0])
        self.assertIn("after=doc_a", requested[1])

    def test_rejects_a_cursor_that_does_not_advance(self) -> None:
        # A stuck cursor would page forever against a live index.
        def fetch(_url: str) -> dict[str, Any]:
            return {"data": [{"document_id": "doc_a"}], "next_after": "doc_a", "limit": 1}

        with self.assertRaises(ProcessingError):
            list(iter_indexed_documents("http://ls", after_document_id="doc_a", page_size=1, fetch_page=fetch))

    def test_rejects_a_response_without_a_data_array(self) -> None:
        with self.assertRaises(ProcessingError):
            list(iter_indexed_documents("http://ls", fetch_page=lambda _url: {"error": "nope"}))


class SummarySerializationTest(unittest.TestCase):
    def test_summary_is_json_serializable_for_operator_diffing(self) -> None:
        summary = ReconcileSummary(indexed_scanned=1, orphaned=1, orphan_document_ids=[ORPHAN_DOC])

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.json"
            path.write_text(json.dumps(summary.to_dict(), sort_keys=True), encoding="utf-8")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["orphaned"], 1)


if __name__ == "__main__":
    unittest.main()
