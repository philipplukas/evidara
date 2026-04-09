import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from document_intelligence.config.runtime import RuntimeSettings, SurfaceUris
from document_intelligence.persist.surfaces import (
    PROCESSING_MANIFESTS,
    PUBLISHED_DOCUMENTS,
    PUBLISHED_SECTIONS,
    get_surface_definition,
)
from document_intelligence.processing_runtime import build_processing_pipeline


class RuntimeSettingsTests(unittest.TestCase):
    def test_builds_surface_uris_from_root_uri(self) -> None:
        uris = SurfaceUris.from_root_uri("gs://bucket/di_surfaces")
        self.assertEqual(
            uris.published_documents_uri,
            "gs://bucket/di_surfaces/published_documents",
        )
        self.assertEqual(
            uris.published_sections_uri,
            "gs://bucket/di_surfaces/published_sections",
        )
        self.assertEqual(
            uris.processing_manifests_uri,
            "gs://bucket/di_surfaces/processing_manifests",
        )

    def test_builds_runtime_settings_from_environment_mapping(self) -> None:
        settings = RuntimeSettings.from_mapping(
            {
                "DI_PROCESSING_VERSION": "di_2026_03_29",
                "DI_SURFACES_ROOT_URI": "/tmp/di-surfaces",
            }
        )
        self.assertEqual(settings.processing_version, "di_2026_03_29")
        self.assertEqual(
            settings.surface_uris.published_documents_uri,
            "/tmp/di-surfaces/published_documents",
        )

    def test_requires_complete_explicit_surface_uris(self) -> None:
        with self.assertRaises(ValueError):
            RuntimeSettings.from_mapping({"DI_PUBLISHED_DOCUMENTS_URI": "/tmp/docs"})

    def test_defaults_parser_backend_and_spacy_toggle(self) -> None:
        settings = RuntimeSettings.from_mapping({})
        self.assertEqual(settings.parser_backend, "legacy")
        self.assertFalse(settings.enable_spacy)
        self.assertEqual(settings.spacy_model_name, "xx_sent_ud_sm")
        self.assertEqual(settings.spacy_max_chars_per_section, 100000)
        self.assertEqual(settings.spacy_batch_size, 32)
        self.assertFalse(settings.enable_llm_extractor)
        self.assertEqual(settings.llm_confidence_threshold, 0.7)

    def test_parses_parser_backend_and_spacy_toggle_from_mapping(self) -> None:
        settings = RuntimeSettings.from_mapping(
            {
                "DI_PARSER_BACKEND": "docling",
                "DI_ENABLE_SPACY": "true",
                "DI_SPACY_MODEL_NAME": "en_core_web_sm",
                "DI_SPACY_MAX_CHARS_PER_SECTION": "777",
                "DI_SPACY_BATCH_SIZE": "8",
                "DI_ENABLE_LLM_EXTRACTOR": "true",
                "DI_LLM_CONFIDENCE_THRESHOLD": "0.9",
            }
        )
        self.assertEqual(settings.parser_backend, "docling")
        self.assertTrue(settings.enable_spacy)
        self.assertEqual(settings.spacy_model_name, "en_core_web_sm")
        self.assertEqual(settings.spacy_max_chars_per_section, 777)
        self.assertEqual(settings.spacy_batch_size, 8)
        self.assertTrue(settings.enable_llm_extractor)
        self.assertEqual(settings.llm_confidence_threshold, 0.9)

    def test_rejects_unknown_parser_backend(self) -> None:
        with self.assertRaises(ValueError):
            RuntimeSettings.from_mapping({"DI_PARSER_BACKEND": "unknown"})

    def test_rejects_invalid_spacy_limits(self) -> None:
        with self.assertRaises(ValueError):
            RuntimeSettings.from_mapping({"DI_SPACY_MAX_CHARS_PER_SECTION": "0"})
        with self.assertRaises(ValueError):
            RuntimeSettings.from_mapping({"DI_SPACY_BATCH_SIZE": "0"})
        with self.assertRaises(ValueError):
            RuntimeSettings.from_mapping({"DI_LLM_CONFIDENCE_THRESHOLD": "1.5"})

    def test_build_processing_pipeline_propagates_runtime_flags(self) -> None:
        settings = RuntimeSettings.from_mapping(
            {
                "DI_PARSER_BACKEND": "docling",
                "DI_ENABLE_SPACY": "true",
                "DI_ENABLE_LLM_EXTRACTOR": "true",
                "DI_LLM_CONFIDENCE_THRESHOLD": "0.85",
            }
        )

        pipeline = build_processing_pipeline(runtime_settings=settings)

        self.assertEqual(pipeline._parser_backend, "docling")
        self.assertTrue(pipeline._enable_spacy)
        self.assertTrue(pipeline._enable_llm_extractor)
        self.assertEqual(pipeline._llm_confidence_threshold, 0.85)


class SurfaceDefinitionTests(unittest.TestCase):
    def test_exposes_expected_surface_definitions(self) -> None:
        document_surface = get_surface_definition("published_documents")
        section_surface = get_surface_definition("published_sections")
        manifest_surface = get_surface_definition("processing_manifests")

        self.assertEqual(document_surface.surface_name, PUBLISHED_DOCUMENTS.surface_name)
        self.assertEqual(section_surface.surface_name, PUBLISHED_SECTIONS.surface_name)
        self.assertEqual(manifest_surface.surface_name, PROCESSING_MANIFESTS.surface_name)
        self.assertIn("document_id", document_surface.column_names())
        self.assertIn("section_id", section_surface.column_names())
        self.assertIn("processing_manifest_id", manifest_surface.column_names())


if __name__ == "__main__":
    unittest.main()
