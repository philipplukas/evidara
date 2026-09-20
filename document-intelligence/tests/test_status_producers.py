"""A declared processing status must have something that writes it (#1045).

`quarantined` was declared on five surfaces — the event contract's enum,
`ProcessingStatus`, `STATUSES_REQUIRING_A_REASON`, the coverage read models and
`CoverageService._quarantined_by_jurisdiction` — and emitted by nothing, from #731
until #1045. Nine months in which `GET /v1/acquisition-coverage` reported
`quarantined_documents: 0`
for a corpus that had refused 117 manifestations, and in which the only number a
reader could get out of the ledger was the one that cannot be true.

Nothing failed, because nothing asked. These tests ask, in two ways that fail for
two different reasons:

* **Declaration** — every status in the contract enum has an entry in
  `STATUS_PRODUCERS`. Adding a status to the enum and stopping there goes red.
* **Emission** — every status `STATUS_PRODUCERS` attributes to *this package* is
  produced by actually running the pipeline and collecting what came out. A claim
  here cannot be satisfied by writing it down.

The second is the one that would have caught #1045. It is deliberately not a grep
for the status literal: `"quarantined"` appears in `pipeline.py` as a manifest
status regardless, so a source scan would have reported a producer that did not
exist.

This is ADR-0052 (*declared means produced*, Proposed) applied to one enum, not the
general gate it asks for — `scripts/check_declared_fields_produced.py` does not exist
yet. It follows the ADR on the two points that decide whether such a gate is worth
anything: **a consumer is not a producer** (§4), and **the escape hatch is the
load-bearing half** (§2) — an absent producer is registered with an issue number, not
silenced.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from document_intelligence.events.status_updated import (
    DOCUMENT_INTELLIGENCE,
    DOCUMENT_INTELLIGENCE_STATUSES,
    PLATFORM_CONTROL,
    STATUS_PRODUCERS,
)
from document_intelligence.persist.sinks import InMemoryCanonicalSink
from document_intelligence.pipeline import ProcessingPipeline
from document_intelligence.validate.schema_validation import load_contract_schema
from support import build_bundle_event, build_manifest_payload

_STATUS_SCHEMA = "events/document-processing-status-updated.schema.json"

# Real legal-text markers and enough body to clear the ADR-0047 floors: a fixture that
# could not pass the gate would be exercising the refusal ending twice and the success
# ending never.
_STATUTE_HTML = """
<html>
  <head><title>Gesetz ueber das Halten von Hunden</title></head>
  <body>
    <h1>Abschnitt 1</h1>
    <p>Art. 1 Abs. 1 Dieses Gesetz regelt das Halten von Hunden im Kantonsgebiet
       sowie die Aufgaben der zustaendigen Behoerden.</p>
    <h2>Abschnitt 2</h2>
    <p>Art. 2 Abs. 1 Wer einen Hund haelt, hat ihn so zu beaufsichtigen, dass
       Menschen und Tiere nicht gefaehrdet werden.</p>
  </body>
</html>
"""

# Structurally fine, textually empty: normalisation produces no blocks at all, which is
# ADR-0047's `no_sections_extracted`. Chosen over an image-only PDF so this file does
# not depend on reportlab — `test_quarantine.py` owns the PDF classes.
#
# The `<title>` really has to be absent. With one, `normalize/html.py` synthesises a
# fallback block from it, the IR is no longer empty, and `text/html` is then exempt from
# the floors as an upstream-assessed modality — so the document reaches
# `canonical_ready` and this file's refusal ending quietly stops existing.
# `test_the_two_endings_are_different_and_both_terminate` is what caught that.
_EMPTY_HTML = "<html><head></head><body></body></html>"


def _statuses_emitted_for(html: str) -> list[str]:
    """Run one document through the pipeline and report the statuses it emitted."""
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as artifact:
        artifact.write(html)
        artifact_path = artifact.name

    payload = build_manifest_payload(artifact_path, artifact_role="primary_document")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump(payload, handle)
        manifest_path = handle.name

    try:
        result = ProcessingPipeline(
            sink=InMemoryCanonicalSink(),
            processing_version="di_2026_09_20",
        ).process_event(build_bundle_event(manifest_path))
    finally:
        os.unlink(artifact_path)
        os.unlink(manifest_path)

    return [event["payload"]["status"] for event in result.status_events]


def _contract_statuses() -> set[str]:
    schema = load_contract_schema(_STATUS_SCHEMA)
    for branch in schema["allOf"]:
        payload = branch.get("properties", {}).get("payload")
        if payload:
            return set(payload["properties"]["status"]["enum"])
    raise AssertionError(f"{_STATUS_SCHEMA} no longer declares a payload status enum")


class StatusProducerDeclarationTests(unittest.TestCase):
    def test_every_contract_status_names_a_producer(self) -> None:
        """MUTATION: drop any key from `STATUS_PRODUCERS` and this fails naming it."""
        declared = _contract_statuses()
        self.assertEqual(
            set(STATUS_PRODUCERS),
            declared,
            "every status the event contract declares must say who writes it, and "
            "STATUS_PRODUCERS must not claim one the contract does not carry",
        )

    def test_a_status_with_no_producer_names_the_issue_tracking_it(self) -> None:
        """`withdrawn` and `skipped_duplicate` are still unwritten, and say so.

        This is the one place in these tests that tolerates an absent producer, so it
        cannot be a bare allowlist: the entry must carry an issue number, which is what
        turns "nobody noticed" into "somebody owes this". `component=None` with an
        empty `where` fails here.
        """
        unproduced = {status for status, producer in STATUS_PRODUCERS.items() if not producer.exists}
        self.assertEqual(unproduced, {"withdrawn", "skipped_duplicate"})
        for status in sorted(unproduced):
            with self.subTest(status=status):
                self.assertRegex(
                    STATUS_PRODUCERS[status].where,
                    r"#\d+",
                    f"{status} has no producer and must name the issue that tracks it",
                )

    def test_every_producer_is_a_component_this_repo_has(self) -> None:
        components = {producer.component for producer in STATUS_PRODUCERS.values()}
        self.assertLessEqual(components, {DOCUMENT_INTELLIGENCE, PLATFORM_CONTROL, None})


class StatusEmissionTests(unittest.TestCase):
    """The claim, checked by running the thing rather than by reading it."""

    def test_document_intelligence_emits_every_status_it_claims(self) -> None:
        """Both endings of the pipeline, and nothing left over.

        MUTATION: delete the `status="quarantined"` event from
        `ProcessingPipeline._quarantine_result` and this fails — `quarantined` is
        claimed in `STATUS_PRODUCERS` and never arrives. Equally, claiming `withdrawn`
        for document-intelligence without writing an emitter fails here too.
        """
        emitted = set(_statuses_emitted_for(_STATUTE_HTML)) | set(_statuses_emitted_for(_EMPTY_HTML))

        self.assertEqual(emitted, set(DOCUMENT_INTELLIGENCE_STATUSES))

    def test_the_two_endings_are_different_and_both_terminate(self) -> None:
        """Guards the guard above: if both fixtures took the same path, the union
        would still be a set and could still match by accident on a smaller claim."""
        success = _statuses_emitted_for(_STATUTE_HTML)
        refused = _statuses_emitted_for(_EMPTY_HTML)

        self.assertEqual(success, ["accepted", "processing", "canonical_ready"])
        self.assertEqual(refused, ["accepted", "processing", "quarantined"])

    def test_no_status_this_package_emits_is_attributed_elsewhere(self) -> None:
        """`failed` is platform-control's (#1042) and must stay that way.

        The reclaim sweep's row means *the control plane stopped waiting*, never
        *document-intelligence reported a failure*. If DI ever starts emitting `failed`,
        those two claims collapse into one status and the distinction #1042 is built on
        is gone — so this fails rather than letting it happen quietly.
        """
        emitted = set(_statuses_emitted_for(_STATUTE_HTML)) | set(_statuses_emitted_for(_EMPTY_HTML))
        foreign = {
            status
            for status, producer in STATUS_PRODUCERS.items()
            if producer.component is not None and producer.component != DOCUMENT_INTELLIGENCE
        }
        self.assertEqual(emitted & foreign, set())
        self.assertIn("failed", foreign)

    def test_the_emitted_statuses_are_all_declared_by_the_contract(self) -> None:
        emitted = set(_statuses_emitted_for(_STATUTE_HTML)) | set(_statuses_emitted_for(_EMPTY_HTML))
        self.assertLessEqual(emitted, _contract_statuses())


if __name__ == "__main__":
    unittest.main()
