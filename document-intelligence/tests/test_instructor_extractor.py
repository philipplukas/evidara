"""Tests for InstructorMetadataExtractor with mocked LLM calls."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from document_intelligence.extractors.instructor_metadata_extractor import (
    InstructorMetadataExtractor,
    LegalDocumentMetadata,
)
from document_intelligence.extractors.profile_config import ExtractionProfileConfig
from document_intelligence.normalize.ir import Block, NormalizedDocumentIR

sys.path.insert(0, os.path.dirname(__file__))
from support import build_manifest_payload


def _sample_ir() -> NormalizedDocumentIR:
    return NormalizedDocumentIR(
        blocks=[
            Block(
                id="blk_0000",
                type="paragraph",
                text="Bundesgesetz über den Schutz personenbezogener Daten",
                level=None,
                order=0,
                parent_id=None,
                artifact_id="art_test",
                attrs={},
            ),
        ],
        metadata={"title": None, "normalizer": "test"},
    )


def load_manifest_from_payload(payload: dict):
    from document_intelligence.contracts.envelope import ArtifactBundleManifest

    return ArtifactBundleManifest.from_dict(payload)


class TestLegalDocumentMetadataSchema(unittest.TestCase):
    def test_valid_schema(self):
        m = LegalDocumentMetadata(title="Test Title", source_family="law", confidence=0.9)
        assert m.title == "Test Title"
        assert m.source_family == "law"

    def test_rejects_empty_title(self):
        with self.assertRaises(Exception):
            LegalDocumentMetadata(title="  ", source_family="law", confidence=0.5)

    def test_rejects_out_of_range_confidence(self):
        with self.assertRaises(Exception):
            LegalDocumentMetadata(title="Title", source_family="law", confidence=1.5)

    def test_strips_title_whitespace(self):
        m = LegalDocumentMetadata(title="  Padded Title  ", source_family="decision", confidence=0.8)
        assert m.title == "Padded Title"


class TestInstructorMetadataExtractor(unittest.TestCase):
    @patch("document_intelligence.extractors.instructor_metadata_extractor._create_instructor_client")
    def test_extract_returns_candidate(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = (mock_client, "gpt-4o-mini")
        mock_client.chat.completions.create.return_value = LegalDocumentMetadata(
            title="Extracted Title",
            source_family="law",
            confidence=0.92,
        )

        profile = ExtractionProfileConfig(
            llm_provider="openai",
            llm_model="gpt-4o-mini",
        )
        extractor = InstructorMetadataExtractor(profile=profile)

        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
            f.write("<html><body>test</body></html>")
            artifact_path = f.name

        payload = build_manifest_payload(artifact_path, artifact_role="primary_document")
        manifest = load_manifest_from_payload(payload)
        primary_artifact = manifest.artifacts[0]

        try:
            candidate = extractor.extract(
                normalized_document=_sample_ir(),
                manifest=manifest,
                primary_artifact=primary_artifact,
            )
            assert candidate is not None
            assert candidate.title == "Extracted Title"
            assert candidate.document_type == "law"
            assert candidate.confidence == 0.92
            assert candidate.provider == "openai"
        finally:
            os.unlink(artifact_path)

    @patch("document_intelligence.extractors.instructor_metadata_extractor._create_instructor_client")
    def test_extract_handles_failure_gracefully(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = (mock_client, "gpt-4o-mini")
        mock_client.chat.completions.create.side_effect = RuntimeError("LLM unavailable")

        profile = ExtractionProfileConfig(
            llm_provider="openai",
            llm_model="gpt-4o-mini",
        )
        extractor = InstructorMetadataExtractor(profile=profile)
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
            f.write("<html><body>test</body></html>")
            artifact_path = f.name

        payload = build_manifest_payload(artifact_path, artifact_role="primary_document")
        manifest = load_manifest_from_payload(payload)
        primary_artifact = manifest.artifacts[0]

        try:
            candidate = extractor.extract(
                normalized_document=_sample_ir(),
                manifest=manifest,
                primary_artifact=primary_artifact,
            )
            assert candidate is not None
            assert candidate.confidence == 0.0
            assert candidate.raw["extraction"]["error"] == "extractor_failed"
        finally:
            os.unlink(artifact_path)


if __name__ == "__main__":
    unittest.main()
