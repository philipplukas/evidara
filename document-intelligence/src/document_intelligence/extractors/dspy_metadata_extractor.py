"""DSPy-backed MetadataExtractor implementation.

Orchestrates TitleExtractor, SourceFamilyClassifier, and CommentaryExtractor
behind the MetadataExtractor protocol. Provider configuration follows ADR-0023.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from document_intelligence.contracts.envelope import (
    ArtifactBundleManifest,
    ArtifactBundleManifestArtifact,
)
from document_intelligence.extractors.metadata import MetadataExtractionCandidate
from document_intelligence.extractors.profile_config import ExtractionProfileConfig
from document_intelligence.normalize.ir import NormalizedDocumentIR

logger = logging.getLogger(__name__)


def _configure_dspy_lm(profile: ExtractionProfileConfig) -> None:
    """Configure the DSPy language model from profile settings."""
    import dspy

    provider = profile.llm_provider
    model = profile.llm_model

    if provider == "vertexai":
        lm = dspy.LM(f"google/vertexai/{model}")
    elif provider == "openai":
        lm = dspy.LM(f"openai/{model}")
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")

    dspy.configure(lm=lm)


def _gather_metadata_hints(
    manifest: ArtifactBundleManifest,
    primary_artifact: ArtifactBundleManifestArtifact,
) -> dict[str, Any]:
    """Collect metadata hints from manifest and artifact for LLM context."""
    hints: dict[str, Any] = {}
    if hasattr(manifest, "di_overrides") and manifest.di_overrides:
        hints["di_overrides"] = manifest.di_overrides
    if hasattr(manifest, "provenance") and manifest.provenance:
        prov = manifest.provenance
        if hasattr(prov, "source_defaults") and prov.source_defaults:
            hints["source_defaults"] = prov.source_defaults
    if hasattr(primary_artifact, "metadata") and primary_artifact.metadata:
        hints["artifact_metadata"] = primary_artifact.metadata
    return hints


class DspyMetadataExtractor:
    """MetadataExtractor implementation using DSPy modules.

    Satisfies the ``MetadataExtractor`` protocol from
    ``document_intelligence.extractors.metadata``.
    """

    def __init__(
        self,
        profile: ExtractionProfileConfig | None = None,
    ) -> None:
        from document_intelligence.extractors.dspy_modules import (
            CommentaryExtractor,
            SourceFamilyClassifier,
            TitleExtractor,
        )

        self._profile = profile or ExtractionProfileConfig.from_environment()
        _configure_dspy_lm(self._profile)

        self._title_extractor = (
            TitleExtractor() if self._profile.enable_title_extractor else None
        )
        self._classifier = (
            SourceFamilyClassifier()
            if self._profile.enable_source_family_classifier
            else None
        )
        self._commentary_extractor = (
            CommentaryExtractor()
            if self._profile.enable_commentary_extractor
            else None
        )

    def extract(
        self,
        *,
        normalized_document: NormalizedDocumentIR,
        manifest: ArtifactBundleManifest,
        primary_artifact: ArtifactBundleManifestArtifact,
    ) -> MetadataExtractionCandidate | None:
        hints = _gather_metadata_hints(manifest, primary_artifact)
        body = normalized_document.full_text

        title: str | None = None
        document_type: str | None = None
        title_confidence = 0.0
        classifier_confidence = 0.0
        raw: dict[str, Any] = {"profile": {
            "provider": self._profile.llm_provider,
            "model": self._profile.llm_model,
        }}

        if self._title_extractor:
            try:
                result = self._title_extractor.extract(body, hints)
                title = result.get("title") or None
                title_confidence = result.get("confidence", 0.0)
                raw["title_extraction"] = result
            except Exception:
                logger.exception("TitleExtractor failed")
                raw["title_extraction"] = {"error": "extractor_failed"}

        if self._classifier:
            try:
                result = self._classifier.classify(body, hints)
                document_type = result.get("source_family") or None
                if document_type == "unknown":
                    document_type = None
                classifier_confidence = result.get("confidence", 0.0)
                raw["source_family_classification"] = result
            except Exception:
                logger.exception("SourceFamilyClassifier failed")
                raw["source_family_classification"] = {"error": "extractor_failed"}

        if self._commentary_extractor and document_type == "commentary":
            try:
                passages = self._commentary_extractor.extract(body)
                raw["commentary_passages"] = passages
            except Exception:
                logger.exception("CommentaryExtractor failed")
                raw["commentary_passages"] = {"error": "extractor_failed"}

        confidences = [
            c for c in [title_confidence, classifier_confidence] if c > 0
        ]
        overall_confidence = (
            sum(confidences) / len(confidences) if confidences else 0.0
        )

        return MetadataExtractionCandidate(
            title=title,
            document_type=document_type,
            confidence=overall_confidence,
            model=self._profile.llm_model,
            provider=self._profile.llm_provider,
            raw=raw,
        )
