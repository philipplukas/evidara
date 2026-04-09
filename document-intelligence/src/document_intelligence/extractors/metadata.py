"""Metadata extractor seam for optional LLM-assisted enrichment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from document_intelligence.contracts.envelope import (
    ArtifactBundleManifest,
    ArtifactBundleManifestArtifact,
)
from document_intelligence.normalize.ir import NormalizedDocumentIR


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
