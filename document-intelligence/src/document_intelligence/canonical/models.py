"""Canonical entities produced by document-intelligence."""

from dataclasses import dataclass, field
from typing import Any

from document_intelligence.contracts.envelope import ManifestRef, Provenance


@dataclass(frozen=True)
class Document:
    document_id: str
    document_revision: int
    processing_manifest_id: str
    provenance: Provenance
    primary_artifact_id: str
    title: str
    processed_at: str
    processing_version: str
    lifecycle_status: str
    full_text: str
    body_text: str
    jurisdiction_id: str | None = None
    authority_id: str | None = None
    document_type: str | None = None
    effective_date: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "document_revision": self.document_revision,
            "processing_manifest_id": self.processing_manifest_id,
            "provenance": self.provenance.to_dict(),
            "primary_artifact_id": self.primary_artifact_id,
            "jurisdiction_id": self.jurisdiction_id,
            "authority_id": self.authority_id,
            "title": self.title,
            "document_type": self.document_type,
            "effective_date": self.effective_date,
            "processed_at": self.processed_at,
            "processing_version": self.processing_version,
            "lifecycle_status": self.lifecycle_status,
            "full_text": self.full_text,
            "body_text": self.body_text,
            "metadata": dict(self.metadata),
            "extensions": dict(self.extensions),
        }


@dataclass(frozen=True)
class Section:
    section_id: str
    document_id: str
    document_revision: int
    processing_manifest_id: str
    provenance: Provenance
    ordinal: int
    depth: int
    content: str
    parent_section_id: str | None = None
    title: str | None = None
    section_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "document_id": self.document_id,
            "document_revision": self.document_revision,
            "processing_manifest_id": self.processing_manifest_id,
            "provenance": self.provenance.to_dict(),
            "parent_section_id": self.parent_section_id,
            "ordinal": self.ordinal,
            "depth": self.depth,
            "title": self.title,
            "content": self.content,
            "section_type": self.section_type,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class CommentaryInsight:
    insight_id: str
    document_id: str
    document_revision: int
    processing_manifest_id: str
    insight_type: str
    claim: str
    display_text: str
    support: list[dict[str, Any]]
    referenced_authorities: list[dict[str, Any]]
    confidence: float
    review_state: str
    generator: dict[str, Any]
    scores: dict[str, float]
    section_id: str | None = None
    citation_id: str | None = None
    language: str | None = None
    jurisdiction_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "insight_id": self.insight_id,
            "document_id": self.document_id,
            "document_revision": self.document_revision,
            "processing_manifest_id": self.processing_manifest_id,
            "section_id": self.section_id,
            "citation_id": self.citation_id,
            "insight_type": self.insight_type,
            "claim": self.claim,
            "display_text": self.display_text,
            "support": list(self.support),
            "referenced_authorities": list(self.referenced_authorities),
            "language": self.language,
            "jurisdiction_id": self.jurisdiction_id,
            "confidence": self.confidence,
            "review_state": self.review_state,
            "generator": dict(self.generator),
            "scores": dict(self.scores),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ProcessingManifest:
    processing_manifest_id: str
    manifest_version: int
    document_id: str
    document_revision: int
    processing_version: str
    status: str
    provenance: Provenance
    input_bundle_manifest_ref: ManifestRef
    selected_profiles: dict[str, str]
    reference_snapshot_set_ref: str | None = None
    published_document_ref: dict[str, Any] | None = None
    published_sections_ref: dict[str, Any] | None = None
    canonical_ready_at: str | None = None
    supersedes_processing_manifest_id: str | None = None
    document_count: int = 0
    section_count: int = 0
    citation_count: int = 0
    failure: dict[str, str] | None = None
    # ADR-0047. Deliberately *not* folded into `failure`: a quarantined document did not
    # fail — processing completed and produced output we should not trust — and the two
    # take opposite remedies (replay vs. implement the missing class). Storing them in one
    # column is what would make the queue undrainable.
    quarantine: dict[str, Any] | None = None
    #: Per-stage timings and counts for this document (#903). Timings and counts
    #: ONLY — a stage entry does not yet say what it removed from the text
    #: (footnote apparatus, page furniture, a lifted Randtitel, a dropped
    #: citation). That is ADR-0044's subject. An empty list therefore means "not
    #: recorded", never "no stages ran": manifests written before this field
    #: existed have none, and so does any path that does not build a ledger.
    stages: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        output = {
            "processing_manifest_id": self.processing_manifest_id,
            "manifest_version": self.manifest_version,
            "document_id": self.document_id,
            "document_revision": self.document_revision,
            "processing_version": self.processing_version,
            "status": self.status,
            "provenance": self.provenance.to_dict(),
            "input_bundle_manifest_ref": self.input_bundle_manifest_ref.to_dict(),
            "selected_profiles": dict(self.selected_profiles),
            "reference_snapshot_set_ref": self.reference_snapshot_set_ref,
            "document_count": self.document_count,
            "section_count": self.section_count,
            "citation_count": self.citation_count,
        }
        if self.published_document_ref is not None:
            output["published_document_ref"] = dict(self.published_document_ref)
        if self.published_sections_ref is not None:
            output["published_sections_ref"] = dict(self.published_sections_ref)
        if self.canonical_ready_at is not None:
            output["canonical_ready_at"] = self.canonical_ready_at
        if self.supersedes_processing_manifest_id is not None:
            output["supersedes_processing_manifest_id"] = self.supersedes_processing_manifest_id
        if self.failure is not None:
            output["failure"] = dict(self.failure)
        if self.quarantine is not None:
            output["quarantine"] = dict(self.quarantine)
        # Omitted when empty rather than emitted as `[]`. An empty array is a
        # claim that the pipeline ran no stages; an absent key is the honest
        # "this manifest does not carry stage timings".
        if self.stages:
            output["stages"] = [dict(stage) for stage in self.stages]
        return output


@dataclass(frozen=True)
class ProcessingResult:
    """Terminal outcome of processing one artifact bundle.

    ``document`` and ``document_processed_event`` are ``None`` exactly when the result is
    quarantined (ADR-0047): no canonical document was published, so there is nothing for
    the projection bridge to forward to legal-search. Callers must branch on
    :attr:`is_quarantined` before dereferencing either — publishing a ``document.processed``
    event for a manifestation we hold no legal text for is the confident fabrication the
    quarantine invariant exists to prevent.
    """

    document: Document | None
    sections: list[Section]
    commentary_insights: list[CommentaryInsight]
    manifest: ProcessingManifest
    status_events: list[dict[str, Any]]
    document_processed_event: dict[str, Any] | None
    quarantine: dict[str, Any] | None = None

    @property
    def is_quarantined(self) -> bool:
        return self.quarantine is not None
