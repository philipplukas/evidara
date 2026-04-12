"""DSPy extraction modules for AI-accelerated metadata enrichment.

Each module is a standalone DSPy module with typed signatures.
See ADR-0023 for rationale, quality targets, and provider strategy.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    import dspy
except ImportError:
    dspy = None  # type: ignore[assignment]


SOURCE_FAMILY_VOCABULARY = frozenset({
    "law",
    "decision",
    "commentary",
    "admin_guidance",
    "unknown",
})


def _require_dspy() -> None:
    if dspy is None:
        raise ImportError(
            "dspy is required for LLM extraction modules. "
            "Install with: uv sync --group llm"
        )


class TitleExtractorSignature(dspy.Signature if dspy else object):  # type: ignore[misc]
    """Extract the canonical legal document title from document text and metadata hints."""

    document_text: str = dspy.InputField(desc="First ~2000 chars of the document body") if dspy else ""  # type: ignore[assignment]
    metadata_hints: str = dspy.InputField(desc="JSON string of available metadata hints (source_defaults, extracted_metadata)") if dspy else ""  # type: ignore[assignment]
    title: str = dspy.OutputField(desc="Extracted canonical title for the legal document") if dspy else ""  # type: ignore[assignment]
    confidence: float = dspy.OutputField(desc="Confidence score between 0.0 and 1.0") if dspy else 0.0  # type: ignore[assignment]


class SourceFamilyClassifierSignature(dspy.Signature if dspy else object):  # type: ignore[misc]
    """Classify a legal document into a source family based on its content and metadata."""

    document_text: str = dspy.InputField(desc="First ~2000 chars of the document body") if dspy else ""  # type: ignore[assignment]
    metadata_hints: str = dspy.InputField(desc="JSON string of available metadata hints") if dspy else ""  # type: ignore[assignment]
    source_family: str = dspy.OutputField(desc="One of: law, decision, commentary, admin_guidance, unknown") if dspy else ""  # type: ignore[assignment]
    confidence: float = dspy.OutputField(desc="Confidence score between 0.0 and 1.0") if dspy else 0.0  # type: ignore[assignment]


class CommentaryExtractorSignature(dspy.Signature if dspy else object):  # type: ignore[misc]
    """Extract commentary passages and referenced legal provisions from a commentary document."""

    document_text: str = dspy.InputField(desc="Full document body text") if dspy else ""  # type: ignore[assignment]
    passages_json: str = dspy.OutputField(desc="JSON array of {passage, referenced_provision, section_ref}") if dspy else ""  # type: ignore[assignment]


class TitleExtractor:
    """Extract document title using DSPy ChainOfThought."""

    def __init__(self, max_text_chars: int = 2000) -> None:
        _require_dspy()
        self._predictor = dspy.ChainOfThought(TitleExtractorSignature)
        self._max_text_chars = max_text_chars

    def extract(
        self,
        document_text: str,
        metadata_hints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        import json

        hints_str = json.dumps(metadata_hints or {}, default=str)
        truncated_text = document_text[: self._max_text_chars]

        result = self._predictor(
            document_text=truncated_text,
            metadata_hints=hints_str,
        )

        title = str(getattr(result, "title", "")).strip()
        try:
            confidence = float(getattr(result, "confidence", 0.0))
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.5

        return {"title": title, "confidence": confidence}


class SourceFamilyClassifier:
    """Classify document into source family using DSPy ChainOfThought."""

    def __init__(self, max_text_chars: int = 2000) -> None:
        _require_dspy()
        self._predictor = dspy.ChainOfThought(SourceFamilyClassifierSignature)
        self._max_text_chars = max_text_chars

    def classify(
        self,
        document_text: str,
        metadata_hints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        import json

        hints_str = json.dumps(metadata_hints or {}, default=str)
        truncated_text = document_text[: self._max_text_chars]

        result = self._predictor(
            document_text=truncated_text,
            metadata_hints=hints_str,
        )

        source_family = str(getattr(result, "source_family", "unknown")).strip().lower()
        if source_family not in SOURCE_FAMILY_VOCABULARY:
            source_family = "unknown"

        try:
            confidence = float(getattr(result, "confidence", 0.0))
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.5

        return {"source_family": source_family, "confidence": confidence}


class CommentaryExtractor:
    """Extract commentary passages and referenced provisions using DSPy."""

    def __init__(self, max_text_chars: int = 8000) -> None:
        _require_dspy()
        self._predictor = dspy.ChainOfThought(CommentaryExtractorSignature)
        self._max_text_chars = max_text_chars

    def extract(self, document_text: str) -> list[dict[str, Any]]:
        import json

        truncated_text = document_text[: self._max_text_chars]
        result = self._predictor(document_text=truncated_text)
        raw_json = str(getattr(result, "passages_json", "[]")).strip()

        try:
            passages = json.loads(raw_json)
            if not isinstance(passages, list):
                passages = []
        except (json.JSONDecodeError, TypeError):
            logger.warning("CommentaryExtractor returned non-JSON: %s", raw_json[:200])
            passages = []

        validated: list[dict[str, Any]] = []
        for p in passages:
            if isinstance(p, dict) and p.get("passage"):
                validated.append({
                    "passage": str(p["passage"]),
                    "referenced_provision": str(p.get("referenced_provision", "")),
                    "section_ref": str(p.get("section_ref", "")),
                })
        return validated
