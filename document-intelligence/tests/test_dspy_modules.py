"""Tests for DSPy extraction modules.

These tests mock the DSPy LM layer so they run without credentials.
They verify module signatures, output validation, and error handling.

They also actually run, as of #685. A module-level `pytest.importorskip("dspy")`
used to drop this entire file from every run — 11 tests over
`extractors/dspy_modules.py`, which is on the production extraction path via
`processing_runtime.py:43` → `dspy_metadata_extractor.py:58`. `dspy` is in the
`llm` extra, which no CI job installed; the suite reported green without ever
naming the file. CI installs `llm` now, and `scripts/ci_skip_guard.py` fails the
run if a skip like that reappears.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _mock_dspy_lm():
    """Patch dspy.configure so no real LM is used."""
    with patch("dspy.configure", return_value=None):
        yield


class _FakePrediction:
    """Simulate a DSPy prediction result with named attributes."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class TestTitleExtractor:
    def test_extracts_title(self):
        from document_intelligence.extractors.dspy_modules import TitleExtractor

        with patch.object(
            TitleExtractor,
            "__init__",
            lambda self, **kw: (
                setattr(self, "_max_text_chars", 2000)
                or setattr(
                    self,
                    "_predictor",
                    MagicMock(
                        return_value=_FakePrediction(
                            title="Bundesgesetz über das Obligationenrecht",
                            confidence=0.92,
                        )
                    ),
                )
            ),
        ):
            ext = TitleExtractor()
            result = ext.extract("Art. 1 OR — Dieses Gesetz regelt...")
            assert result["title"] == "Bundesgesetz über das Obligationenrecht"
            assert result["confidence"] == pytest.approx(0.92)

    def test_clamps_confidence(self):
        from document_intelligence.extractors.dspy_modules import TitleExtractor

        with patch.object(
            TitleExtractor,
            "__init__",
            lambda self, **kw: (
                setattr(self, "_max_text_chars", 2000)
                or setattr(self, "_predictor", MagicMock(return_value=_FakePrediction(title="Test", confidence=1.5)))
            ),
        ):
            ext = TitleExtractor()
            result = ext.extract("Some text")
            assert result["confidence"] == 1.0

    def test_handles_non_numeric_confidence(self):
        from document_intelligence.extractors.dspy_modules import TitleExtractor

        with patch.object(
            TitleExtractor,
            "__init__",
            lambda self, **kw: (
                setattr(self, "_max_text_chars", 2000)
                or setattr(self, "_predictor", MagicMock(return_value=_FakePrediction(title="Test", confidence="high")))
            ),
        ):
            ext = TitleExtractor()
            result = ext.extract("Some text")
            assert result["confidence"] == 0.5


class TestSourceFamilyClassifier:
    def test_classifies_law(self):
        from document_intelligence.extractors.dspy_modules import SourceFamilyClassifier

        with patch.object(
            SourceFamilyClassifier,
            "__init__",
            lambda self, **kw: (
                setattr(self, "_max_text_chars", 2000)
                or setattr(
                    self, "_predictor", MagicMock(return_value=_FakePrediction(source_family="law", confidence=0.95))
                )
            ),
        ):
            clf = SourceFamilyClassifier()
            result = clf.classify("Bundesgesetz vom 30. März 1911")
            assert result["source_family"] == "law"
            assert result["confidence"] == pytest.approx(0.95)

    def test_normalizes_unknown_family(self):
        from document_intelligence.extractors.dspy_modules import SourceFamilyClassifier

        with patch.object(
            SourceFamilyClassifier,
            "__init__",
            lambda self, **kw: (
                setattr(self, "_max_text_chars", 2000)
                or setattr(
                    self,
                    "_predictor",
                    MagicMock(return_value=_FakePrediction(source_family="regulation", confidence=0.3)),
                )
            ),
        ):
            clf = SourceFamilyClassifier()
            result = clf.classify("Some text")
            assert result["source_family"] == "unknown"


class TestCommentaryExtractor:
    def test_extracts_passages(self):
        import json

        from document_intelligence.extractors.dspy_modules import CommentaryExtractor

        passages = [
            {
                "passage": "Art. 41 OR establishes...",
                "referenced_provision": "Art. 41 OR",
                "section_ref": "§2.1",
            }
        ]
        with patch.object(
            CommentaryExtractor,
            "__init__",
            lambda self, **kw: (
                setattr(self, "_max_text_chars", 8000)
                or setattr(
                    self, "_predictor", MagicMock(return_value=_FakePrediction(passages_json=json.dumps(passages)))
                )
            ),
        ):
            ext = CommentaryExtractor()
            result = ext.extract("Commentary on OR Art. 41...")
            assert len(result) == 1
            assert result[0]["passage"] == "Art. 41 OR establishes..."
            assert result[0]["referenced_provision"] == "Art. 41 OR"

    def test_handles_invalid_json(self):
        from document_intelligence.extractors.dspy_modules import CommentaryExtractor

        with patch.object(
            CommentaryExtractor,
            "__init__",
            lambda self, **kw: (
                setattr(self, "_max_text_chars", 8000)
                or setattr(self, "_predictor", MagicMock(return_value=_FakePrediction(passages_json="not json")))
            ),
        ):
            ext = CommentaryExtractor()
            result = ext.extract("Some text")
            assert result == []


class TestProfileConfig:
    def test_defaults(self):
        from document_intelligence.extractors.profile_config import (
            ExtractionProfileConfig,
        )

        config = ExtractionProfileConfig()
        assert config.enable_title_extractor is True
        assert config.enable_source_family_classifier is True
        assert config.enable_commentary_extractor is False
        assert config.llm_provider == "vertexai"
        assert config.llm_model == "gemini-2.0-flash"

    def test_from_environment(self):
        from document_intelligence.extractors.profile_config import (
            ExtractionProfileConfig,
        )

        env = {
            "DI_ENABLE_TITLE_EXTRACTOR": "false",
            "DI_ENABLE_SOURCE_FAMILY_CLASSIFIER": "true",
            "DI_ENABLE_COMMENTARY_EXTRACTOR": "true",
            "DI_LLM_PROVIDER": "openai",
            "DI_LLM_MODEL": "gpt-4o",
        }
        config = ExtractionProfileConfig.from_environment(env)
        assert config.enable_title_extractor is False
        assert config.enable_source_family_classifier is True
        assert config.enable_commentary_extractor is True
        assert config.llm_provider == "openai"
        assert config.llm_model == "gpt-4o"


class TestDspyMetadataExtractor:
    def test_extract_produces_candidate(self):
        from unittest.mock import MagicMock

        from document_intelligence.extractors.dspy_metadata_extractor import (
            DspyMetadataExtractor,
        )
        from document_intelligence.extractors.profile_config import (
            ExtractionProfileConfig,
        )

        profile = ExtractionProfileConfig(
            enable_title_extractor=True,
            enable_source_family_classifier=True,
            enable_commentary_extractor=False,
            llm_provider="openai",
            llm_model="gpt-4o-mini",
        )

        with patch("document_intelligence.extractors.dspy_metadata_extractor._configure_dspy_lm"):
            with (
                patch("document_intelligence.extractors.dspy_modules.TitleExtractor") as MockTitle,
                patch("document_intelligence.extractors.dspy_modules.SourceFamilyClassifier") as MockClassifier,
            ):
                MockTitle.return_value.extract.return_value = {
                    "title": "Bundesgesetz",
                    "confidence": 0.9,
                }
                MockClassifier.return_value.classify.return_value = {
                    "source_family": "law",
                    "confidence": 0.85,
                }

                extractor = DspyMetadataExtractor(profile=profile)
                ir = MagicMock()
                ir.full_text = "Art. 1 Dieses Gesetz..."
                manifest = MagicMock()
                manifest.di_overrides = {}
                manifest.source_defaults = {}
                manifest.bundle_metadata = {}
                artifact = MagicMock()
                artifact.extra_fields = {}

                candidate = extractor.extract(
                    normalized_document=ir,
                    manifest=manifest,
                    primary_artifact=artifact,
                )

                assert candidate is not None
                assert candidate.title == "Bundesgesetz"
                assert candidate.document_type == "law"
                assert candidate.confidence == pytest.approx(0.875)
                assert candidate.provider == "openai"
                assert candidate.model == "gpt-4o-mini"


def test_gather_metadata_hints_for_llm_contract_aligned():
    """Hints must come from manifest.source_defaults / bundle_metadata and artifact.extra_fields."""
    import os
    import sys
    import tempfile

    from document_intelligence.contracts.envelope import ArtifactBundleManifest
    from document_intelligence.extractors.metadata import gather_metadata_hints_for_llm

    sys.path.insert(0, os.path.dirname(__file__))
    from support import build_manifest_payload

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write("<html><title>x</title></html>")
        artifact_path = f.name
    try:
        payload = build_manifest_payload(artifact_path, artifact_role="primary_document")
        payload["bundle_metadata"] = {"extraction_hints": {"title_hint": "From bundle_metadata"}}
        payload["artifacts"][0]["crawl_sidecar"] = {"page_title": "From artifact extra"}
        manifest = ArtifactBundleManifest.from_dict(payload)
        primary = manifest.artifacts[0]
        hints = gather_metadata_hints_for_llm(manifest, primary)
        assert "source_defaults" in hints
        assert hints["bundle_metadata"]["extraction_hints"]["title_hint"] == "From bundle_metadata"
        assert hints["artifact_extra_fields"]["crawl_sidecar"]["page_title"] == "From artifact extra"
    finally:
        os.unlink(artifact_path)
