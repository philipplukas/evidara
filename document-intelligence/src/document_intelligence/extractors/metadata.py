"""Metadata extractor seam for optional LLM-assisted enrichment."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from document_intelligence.contracts.envelope import (
    ArtifactBundleManifest,
    ArtifactBundleManifestArtifact,
)
from document_intelligence.normalize.ir import NormalizedDocumentIR

SourceTier = Literal["structured", "manifest", "llm", "spacy", "docling", "heuristic"]


def gather_metadata_hints_for_llm(
    manifest: ArtifactBundleManifest,
    primary_artifact: ArtifactBundleManifestArtifact,
) -> dict[str, Any]:
    """Collect manifest and primary-artifact hints for LLM extraction.

    Uses only fields defined on the bundle manifest contract (``source_defaults``,
    ``bundle_metadata``, ``di_overrides``) and artifact ``extra_fields`` — not
    optional attributes that only exist on test doubles.
    """
    hints: dict[str, Any] = {}
    if manifest.di_overrides:
        hints["di_overrides"] = dict(manifest.di_overrides)
    if manifest.source_defaults:
        hints["source_defaults"] = dict(manifest.source_defaults)
    if manifest.bundle_metadata:
        hints["bundle_metadata"] = dict(manifest.bundle_metadata)
    if primary_artifact.extra_fields:
        hints["artifact_extra_fields"] = dict(primary_artifact.extra_fields)
    return hints


@dataclass(frozen=True)
class ResolvedField:
    """A metadata field with provenance tracking.

    Records which extraction tier produced the value and the associated confidence.
    """

    value: Any
    source: SourceTier
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "source": self.source,
            "confidence": self.confidence,
        }


@dataclass
class FieldProvenanceAudit:
    """Collects provenance for all resolved metadata fields."""

    fields: dict[str, ResolvedField] = field(default_factory=dict)

    def set(self, name: str, value: Any, source: SourceTier, confidence: float = 1.0) -> None:
        if value is not None and name not in self.fields:
            self.fields[name] = ResolvedField(value=value, source=source, confidence=confidence)

    def set_if_missing(self, name: str, value: Any, source: SourceTier, confidence: float = 1.0) -> None:
        """Set a field only if not already resolved by a higher-priority tier."""
        if value is not None and name not in self.fields:
            self.fields[name] = ResolvedField(value=value, source=source, confidence=confidence)

    def get_value(self, name: str) -> Any:
        rf = self.fields.get(name)
        return rf.value if rf else None

    def to_dict(self) -> dict[str, dict[str, Any]]:
        return {name: rf.to_dict() for name, rf in self.fields.items()}


@dataclass(frozen=True)
class MetadataExtractionCandidate:
    """Candidate metadata returned by an optional extractor."""

    title: str | None = None
    document_type: str | None = None
    summary: str | None = None
    confidence: float = 0.0
    model: str | None = None
    provider: str | None = None
    raw: dict[str, Any] | None = None

    def to_metadata(self, *, applied: bool) -> dict[str, Any]:
        payload = {
            "enabled": True,
            "applied": applied,
            "confidence": self.confidence,
        }
        if self.model:
            payload["model"] = self.model
        if self.provider:
            payload["provider"] = self.provider
        if self.summary:
            payload["summary"] = self.summary
        if self.title:
            payload["title"] = self.title
        if self.document_type:
            payload["document_type"] = self.document_type
        if self.raw:
            payload["raw"] = dict(self.raw)
        return payload


class MetadataExtractor(Protocol):
    """Interface for optional metadata extraction providers."""

    def extract(
        self,
        *,
        normalized_document: NormalizedDocumentIR,
        manifest: ArtifactBundleManifest,
        primary_artifact: ArtifactBundleManifestArtifact,
    ) -> MetadataExtractionCandidate | None: ...
