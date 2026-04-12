"""Optional spaCy-based enrichment helpers.

Supports two modes:
1. Basic sentencization (default, no LLM needed)
2. spaCy-LLM legal NER when the `spacy-llm` package and an LLM backend are configured
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_LEGAL_NER_LABELS = ["COURT", "STATUTE", "DATE", "PARTY", "ECLI", "LEGAL_REF"]

_LEGAL_NER_EXAMPLES = [
    {
        "text": (
            "Der Verfassungsgerichtshof hat in seiner Entscheidung vom 15. Jänner 2026, "
            "ECLI:AT:VFGH:2026:V258.2025, § 12 DSG für verfassungswidrig erklärt."
        ),
        "entities": {
            "COURT": ["Verfassungsgerichtshof"],
            "DATE": ["15. Jänner 2026"],
            "ECLI": ["ECLI:AT:VFGH:2026:V258.2025"],
            "STATUTE": ["§ 12 DSG"],
        },
    },
    {
        "text": "Gemäß Art. 6 EMRK hat der Verwaltungsgerichtshof den Beschwerdeführer Müller GmbH angehört.",
        "entities": {
            "STATUTE": ["Art. 6 EMRK"],
            "COURT": ["Verwaltungsgerichtshof"],
            "PARTY": ["Müller GmbH"],
        },
    },
]


def _build_legal_ner_config() -> dict[str, Any]:
    """Build a spaCy-LLM NER configuration for legal entities."""
    return {
        "task": {
            "@llm_tasks": "spacy.NER.v3",
            "labels": _LEGAL_NER_LABELS,
            "description": (
                "Extract legal entities from Austrian/German/Swiss legal texts. "
                "COURT = court or tribunal names, STATUTE = law references (§, Art.), "
                "DATE = dates, PARTY = parties/persons/organizations, "
                "ECLI = European Case Law Identifiers, LEGAL_REF = other legal references."
            ),
            "examples": _LEGAL_NER_EXAMPLES,
        },
        "model": {
            "@llm_models": "spacy.GPT-4o-Mini.v2",
        },
    }


def _try_build_llm_pipeline(model_name: str) -> tuple[Any, str] | None:
    """Attempt to build a spaCy pipeline with LLM-backed NER.

    Returns (nlp, backend_name) on success, None if unavailable.
    """
    llm_ner_enabled = os.environ.get("DI_SPACY_LLM_NER", "").strip().lower() in {"1", "true", "yes"}
    if not llm_ner_enabled:
        return None

    try:
        import spacy  # type: ignore
        from spacy_llm.util import assemble  # type: ignore  # noqa: F401
    except ImportError:
        return None

    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not openai_key:
        logger.debug("DI_SPACY_LLM_NER enabled but OPENAI_API_KEY not set; falling back to basic pipeline")
        return None

    try:
        nlp = spacy.blank("xx")
        config = _build_legal_ner_config()
        nlp.add_pipe("llm", config=config)
        if "sentencizer" not in nlp.pipe_names:
            nlp.add_pipe("sentencizer", first=True)
        return nlp, "spacy_llm_ner"
    except Exception:
        logger.exception("Failed to initialize spaCy-LLM NER pipeline")
        return None


def enrich_with_spacy(
    text: str,
    *,
    enabled: bool,
    model_name: str,
    max_chars_per_section: int,
    batch_size: int,
) -> dict[str, Any]:
    """Return a small enrichment payload for metadata with optional LLM NER."""
    if not enabled:
        return {
            "enabled": False,
            "backend": "disabled",
            "model_name": model_name,
            "max_chars_per_section": max_chars_per_section,
            "batch_size": batch_size,
            "sentences": [],
            "entities": [],
        }

    try:
        import spacy  # type: ignore
    except ImportError:
        return {
            "enabled": True,
            "backend": "unavailable",
            "model_name": model_name,
            "max_chars_per_section": max_chars_per_section,
            "batch_size": batch_size,
            "sentences": [],
            "entities": [],
        }

    text_window = (text or "")[:max_chars_per_section]

    llm_result = _try_build_llm_pipeline(model_name)
    if llm_result is not None:
        nlp, backend = llm_result
    else:
        try:
            nlp = spacy.load(model_name)
            backend = "spacy_model"
        except Exception:
            nlp = spacy.blank("xx")
            backend = "spacy_blank_xx"

        if "sentencizer" not in nlp.pipe_names:
            nlp.add_pipe("sentencizer")

    docs = list(nlp.pipe([text_window], batch_size=batch_size))
    doc = docs[0] if docs else nlp("")
    sentences: list[str] = [span.text.strip() for span in doc.sents if span.text.strip()]
    entities = [{"text": ent.text, "label": ent.label_} for ent in doc.ents if ent.text and ent.label_]
    return {
        "enabled": True,
        "backend": backend,
        "model_name": model_name,
        "max_chars_per_section": max_chars_per_section,
        "batch_size": batch_size,
        "sentences": sentences,
        "entities": entities,
    }
