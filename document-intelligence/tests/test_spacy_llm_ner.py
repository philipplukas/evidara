"""Tests for spaCy-LLM legal NER pipeline configuration."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from document_intelligence.nlp.spacy_pipeline import (
    _LEGAL_NER_LABELS,
    _build_legal_ner_config,
    enrich_with_spacy,
)


def _has_spacy() -> bool:
    try:
        import spacy  # noqa: F401

        return True
    except ImportError:
        return False


_HAS_SPACY = _has_spacy()


class TestLegalNerConfig(unittest.TestCase):
    def test_config_has_expected_labels(self):
        config = _build_legal_ner_config()
        assert config["task"]["labels"] == _LEGAL_NER_LABELS
        assert "COURT" in config["task"]["labels"]
        assert "ECLI" in config["task"]["labels"]
        assert "STATUTE" in config["task"]["labels"]

    def test_config_has_examples(self):
        config = _build_legal_ner_config()
        examples = config["task"]["examples"]
        assert len(examples) >= 2
        assert "entities" in examples[0]


class TestEnrichWithSpacyBasicMode(unittest.TestCase):
    def test_disabled_returns_empty_enrichment(self):
        result = enrich_with_spacy(
            "Test text",
            enabled=False,
            model_name="xx_sent_ud_sm",
            max_chars_per_section=5000,
            batch_size=1,
        )
        assert result["enabled"] is False
        assert result["backend"] == "disabled"

    @unittest.skipUnless(_HAS_SPACY, "spacy not installed")
    def test_basic_sentencization_works(self):
        result = enrich_with_spacy(
            "First sentence. Second sentence.",
            enabled=True,
            model_name="xx_sent_ud_sm",
            max_chars_per_section=5000,
            batch_size=1,
        )
        assert result["enabled"] is True
        assert result["backend"] in {"spacy_model", "spacy_blank_xx"}
        assert len(result["sentences"]) >= 1

    @unittest.skipUnless(_HAS_SPACY, "spacy not installed")
    @patch.dict(os.environ, {"DI_SPACY_LLM_NER": "0"})
    def test_llm_ner_not_triggered_when_disabled(self):
        result = enrich_with_spacy(
            "Der Verfassungsgerichtshof hat entschieden.",
            enabled=True,
            model_name="xx_sent_ud_sm",
            max_chars_per_section=5000,
            batch_size=1,
        )
        assert result["backend"] != "spacy_llm_ner"

    @unittest.skipUnless(_HAS_SPACY, "spacy not installed")
    @patch.dict(os.environ, {"DI_SPACY_LLM_NER": "1", "OPENAI_API_KEY": ""})
    def test_llm_ner_falls_back_without_api_key(self):
        result = enrich_with_spacy(
            "Der Verfassungsgerichtshof hat entschieden.",
            enabled=True,
            model_name="xx_sent_ud_sm",
            max_chars_per_section=5000,
            batch_size=1,
        )
        assert result["backend"] != "spacy_llm_ner"


if __name__ == "__main__":
    unittest.main()
