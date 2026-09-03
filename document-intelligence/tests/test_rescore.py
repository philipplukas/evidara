from __future__ import annotations

import json
import os
import tempfile
import unittest
from typing import Any

from document_intelligence.config.runtime import RuntimeSettings
from document_intelligence.processing_runtime import build_processing_pipeline
from document_intelligence.rescore import rescore_targeted
from support import build_bundle_event, build_manifest_payload


class FakeRescoreStore:
    def __init__(
        self,
        *,
        document: dict[str, Any] | None,
        manifest: dict[str, Any] | None,
        insight: dict[str, Any] | None = None,
    ) -> None:
        self.document = document
        self.manifest = manifest
        self.insight = insight
        self.document_lookups: list[tuple[str, str | None]] = []

    def get_document(
        self,
        document_id: str,
        processing_manifest_id: str | None = None,
    ) -> dict[str, Any] | None:
        self.document_lookups.append((document_id, processing_manifest_id))
        if self.document is None or self.document.get("document_id") != document_id:
            return None
        if processing_manifest_id and self.document.get("processing_manifest_id") != processing_manifest_id:
            return None
        return self.document

    def get_processing_manifest(self, processing_manifest_id: str) -> dict[str, Any] | None:
        if self.manifest is None or self.manifest.get("processing_manifest_id") != processing_manifest_id:
            return None
        return self.manifest

    def get_commentary_insight(self, insight_id: str) -> dict[str, Any] | None:
        if self.insight is None or self.insight.get("insight_id") != insight_id:
            return None
        return self.insight


class RescoreTargetedTests(unittest.IsolatedAsyncioTestCase):
    async def test_document_returns_unchanged_for_same_semantic_output(self) -> None:
        with _bundle("<html><head><title>T</title></head><body><h1>A</h1><p>B</p></body></html>") as event:
            result = build_processing_pipeline(runtime_settings=RuntimeSettings.from_mapping({})).process_event(event)
            store = _store_from_result(result)

            outcome, run_id = await rescore_targeted(
                target_entity_type="document",
                target_entity_id=result.document.document_id,
                correction_id="cor_01jq7000000000000000000000",
                runtime_settings=RuntimeSettings.from_mapping({}),
                surface_store=store,
                persist_changes=False,
            )

        self.assertEqual(outcome, "unchanged")
        self.assertIsNone(run_id)

    async def test_document_returns_changed_and_run_id_for_semantic_delta(self) -> None:
        with _bundle("<html><head><title>T</title></head><body><h1>A</h1><p>B</p></body></html>") as event:
            result = build_processing_pipeline(runtime_settings=RuntimeSettings.from_mapping({})).process_event(event)
            store = _store_from_result(result)
            assert store.document is not None
            store.document["title"] = "Old title"

            outcome, run_id = await rescore_targeted(
                target_entity_type="document",
                target_entity_id=result.document.document_id,
                correction_id="cor_01jq7000000000000000000001",
                runtime_settings=RuntimeSettings.from_mapping({}),
                surface_store=store,
                persist_changes=False,
            )

        self.assertEqual(outcome, "changed")
        self.assertIsNotNone(run_id)
        self.assertTrue(str(run_id).startswith("run_"))

    async def test_missing_document_returns_failed(self) -> None:
        store = FakeRescoreStore(document=None, manifest=None)

        outcome, run_id = await rescore_targeted(
            target_entity_type="document",
            target_entity_id="doc_01jq7bdptzqv3xs0c41xpw1ybg",
            correction_id="cor_01jq7000000000000000000002",
            runtime_settings=RuntimeSettings.from_mapping({}),
            surface_store=store,
            persist_changes=False,
        )

        self.assertEqual(outcome, "failed")
        self.assertIsNone(run_id)

    async def test_quarantined_reextraction_does_not_crash_and_does_not_persist(self) -> None:
        """A rescore whose re-extraction now quarantines must not dereference a null document.

        `_target_changed` -> `_candidate_document_semantic` reads `candidate.document`, which
        is `None` exactly when quarantined (ADR-0047). Without the guard this raised
        `AttributeError` into `rescore_targeted`'s blanket `except Exception`, so the
        correction workflow recorded a bare "failed" with the real reason nowhere — for the
        one condition ADR-0047 says must never be conflated with failure.

        `text/plain` because the legal-text floors apply to the modalities `content_gate`
        abstains on; the tightened floor models an operator narrowing it after publication.
        """
        legal_text = (
            "Art. 1 Abs. 1 Dieses Gesetz regelt die Erhebung und Bearbeitung von "
            "personenbezogenen Daten durch die zustaendigen Behoerden des Bundes.\n"
            "Art. 2 Abs. 1 Es gilt fuer alle Bundesstellen sowie fuer beauftragte "
            "Dritte, soweit keine besonderen Bestimmungen entgegenstehen.\n"
        )
        with _bundle(legal_text, content_type="text/plain") as event:
            published = build_processing_pipeline(runtime_settings=RuntimeSettings.from_mapping({})).process_event(
                event
            )
            self.assertFalse(published.is_quarantined)
            store = _store_from_result(published)

            tightened = RuntimeSettings.from_mapping({"DI_QUARANTINE_MIN_EXTRACTED_CHARS": "1000000"})
            with self.assertLogs("document_intelligence.rescore", level="WARNING") as logs:
                outcome, run_id = await rescore_targeted(
                    target_entity_type="document",
                    target_entity_id=published.document.document_id,
                    correction_id="cor_01jq7000000000000000000009",
                    runtime_settings=tightened,
                    surface_store=store,
                    persist_changes=True,
                )

        self.assertEqual(outcome, "failed")
        self.assertIsNone(run_id)
        # The reason is named, not swallowed — and it is a quarantine, not a crash.
        self.assertTrue(any("targeted_rescore_quarantined" in line for line in logs.output))
        self.assertFalse(
            any("AttributeError" in line for line in logs.output),
            "the quarantined candidate was dereferenced instead of being handled",
        )

    async def test_invalid_manifest_returns_failed(self) -> None:
        with _bundle("<html><body><h1>A</h1><p>B</p></body></html>") as event:
            result = build_processing_pipeline(runtime_settings=RuntimeSettings.from_mapping({})).process_event(event)
            store = _store_from_result(result)
            assert store.manifest is not None
            store.manifest.pop("input_bundle_manifest_ref", None)

            outcome, run_id = await rescore_targeted(
                target_entity_type="document",
                target_entity_id=result.document.document_id,
                correction_id="cor_01jq7000000000000000000003",
                runtime_settings=RuntimeSettings.from_mapping({}),
                surface_store=store,
                persist_changes=False,
            )

        self.assertEqual(outcome, "failed")
        self.assertIsNone(run_id)

    async def test_commentary_insight_resolves_to_source_document(self) -> None:
        html = """
        <html><head><title>Kommentar zu Art. 754 OR</title></head><body>
          <h1>Art. 754 OR</h1>
          <p>Art. 754 OR wird in der Lehre als Haftungsnorm fuer Organe erlaeutert.</p>
        </body></html>
        """
        settings = RuntimeSettings.from_mapping({"DI_ENABLE_COMMENTARY_INSIGHTS": "true"})
        with _bundle(html, document_type_hint="commentary") as event:
            result = build_processing_pipeline(runtime_settings=settings).process_event(event)
            self.assertGreater(len(result.commentary_insights), 0)
            insight = result.commentary_insights[0].to_dict()
            store = _store_from_result(result, insight=insight)

            outcome, run_id = await rescore_targeted(
                target_entity_type="commentary_insight",
                target_entity_id=insight["insight_id"],
                correction_id="cor_01jq7000000000000000000004",
                runtime_settings=settings,
                surface_store=store,
                persist_changes=False,
            )

        self.assertEqual(outcome, "unchanged")
        self.assertIsNone(run_id)
        self.assertEqual(
            store.document_lookups[-1],
            (result.document.document_id, result.document.processing_manifest_id),
        )


def _store_from_result(
    result,
    *,
    insight: dict[str, Any] | None = None,
) -> FakeRescoreStore:
    document = result.document.to_dict()
    document["sections"] = [section.to_dict() for section in result.sections]
    return FakeRescoreStore(
        document=document,
        manifest=result.manifest.to_dict(),
        insight=insight,
    )


class _bundle:
    def __init__(
        self,
        html: str,
        *,
        document_type_hint: str = "statute",
        content_type: str = "text/html",
    ) -> None:
        self._html = html
        self._document_type_hint = document_type_hint
        self._content_type = content_type
        self._temp_dir: tempfile.TemporaryDirectory[str] | None = None

    def __enter__(self) -> dict[str, Any]:
        self._temp_dir = tempfile.TemporaryDirectory()
        artifact_path = os.path.join(self._temp_dir.name, "document.html")
        manifest_path = os.path.join(self._temp_dir.name, "bundle-manifest.json")
        with open(artifact_path, "w", encoding="utf-8") as handle:
            handle.write(self._html)
        manifest = build_manifest_payload(
            artifact_path,
            artifact_role="primary_document",
            content_type=self._content_type,
        )
        manifest["source_defaults"]["document_type_hint"] = self._document_type_hint
        if self._document_type_hint == "commentary":
            manifest["source_defaults"]["authority_id"] = "auth_commentary_publisher"
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle)
        return build_bundle_event(manifest_path)

    def __exit__(self, *args: object) -> None:
        if self._temp_dir is not None:
            self._temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
