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


class DeltaRescoreSurfaceStoreTests(unittest.TestCase):
    """Cover the store the runtime actually builds (#847).

    Every other test in this module drives ``rescore_targeted`` through
    ``FakeRescoreStore``, so ``DeltaRescoreSurfaceStore`` — the only store
    ``_store_from_settings`` ever constructs — was executed by nothing. That is how
    ``_read_delta_rows`` shipped with no ``storage_options``: against MinIO reached
    through ``DI_S3_*`` alone, which is the self-hosted deployment's entire
    configuration, every rescore read failed with *"the credential provider was not
    enabled: no providers in chain provided credentials"*.
    """

    def test_reads_a_real_delta_surface_end_to_end(self) -> None:
        """A real write and a real read, not an assertion about a constructed object.

        Local filesystem, so no credentials are involved — this pins the read path
        itself (filters, revision ordering, the sections join) and exercises the local
        branch of ``delta_dataset_filesystem`` now that one is passed.
        """
        import importlib.util
        import sys

        if importlib.util.find_spec("deltalake") is None:
            self.skipTest("deltalake is not installed")

        sys.path.insert(0, os.path.dirname(__file__))
        from document_intelligence.config.runtime import SurfaceUris
        from document_intelligence.persist.sinks import DeltaCanonicalSink
        from document_intelligence.rescore import DeltaRescoreSurfaceStore
        from test_adapters import build_processing_result

        with tempfile.TemporaryDirectory() as temp_dir:
            surface_uris = SurfaceUris.from_root_uri(temp_dir)
            result = build_processing_result()
            DeltaCanonicalSink(surface_uris.to_delta_sink_config()).persist(
                result.document, result.sections, result.manifest
            )

            store = DeltaRescoreSurfaceStore(surface_uris)
            document = store.get_document(result.document.document_id)
            self.assertIsNotNone(document)
            self.assertEqual(document["document_id"], result.document.document_id)
            self.assertEqual(len(document.get("sections") or []), len(result.sections))

            manifest = store.get_processing_manifest(result.manifest.processing_manifest_id)
            self.assertIsNotNone(manifest)
            self.assertEqual(
                manifest["processing_manifest_id"],
                result.manifest.processing_manifest_id,
            )

            self.assertIsNone(store.get_document("doc_01hx00000000000000000000zz"))

    def test_every_surface_read_carries_the_s3_credentials(self) -> None:
        """The credentials must reach ``DeltaTable`` on every surface, not just one.

        The real proof is ``tests/test_delta_s3_integration.py``, which reads this store
        over a live MinIO — no assertion about a constructed object can show that a read
        succeeds. This is the part that runs without Docker: on the unfixed code
        ``storage_options`` is absent from every call, which is the defect exactly.
        """
        import sys
        import types

        from document_intelligence.config.runtime import SurfaceUris
        from document_intelligence.persist.sinks import delta_storage_options
        from document_intelligence.rescore import DeltaRescoreSurfaceStore

        environ = {
            "DI_S3_ENDPOINT_URL": "http://minio.internal:9000",
            "DI_S3_ACCESS_KEY_ID": "key",
            "DI_S3_SECRET_ACCESS_KEY": "secret",
            "DI_S3_REGION": "us-east-1",
        }
        expected = delta_storage_options(environ)
        self.assertTrue(expected, "delta_storage_options must map DI_S3_* onto AWS_*")

        seen: list[tuple[str, Any]] = []

        class _StubDeltaTable:
            def __init__(self, uri: str, **kwargs: Any) -> None:
                seen.append((uri, kwargs.get("storage_options")))

            def to_pyarrow_dataset(self, filesystem: Any = None) -> Any:
                return self

            def to_table(self, **kwargs: Any) -> Any:
                return self

            def to_pylist(self) -> list[dict[str, Any]]:
                return []

        stub = types.ModuleType("deltalake")
        stub.DeltaTable = _StubDeltaTable
        original_module = sys.modules.get("deltalake")
        original_environ = {key: os.environ.get(key) for key in environ}
        sys.modules["deltalake"] = stub
        os.environ.update(environ)
        try:
            surface_uris = SurfaceUris.from_root_uri("s3://evidara-lakehouse/canonical")
            store = DeltaRescoreSurfaceStore(surface_uris)
            store.get_document("doc_01hx00000000000000000000zz")
            store.get_processing_manifest("pm_01hx00000000000000000000zz")
            store.get_commentary_insight("ins_01hx00000000000000000000zz")
        finally:
            if original_module is None:
                del sys.modules["deltalake"]
            else:
                sys.modules["deltalake"] = original_module
            for key, value in original_environ.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.assertEqual(
            [uri for uri, _ in seen],
            [
                "s3://evidara-lakehouse/canonical/published_documents",
                "s3://evidara-lakehouse/canonical/processing_manifests",
                "s3://evidara-lakehouse/canonical/published_commentary_insights",
            ],
        )
        for uri, options in seen:
            self.assertEqual(options, expected, f"{uri} was read without S3 credentials")


if __name__ == "__main__":
    unittest.main()
