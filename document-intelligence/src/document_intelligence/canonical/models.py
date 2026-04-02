"""Canonical entities produced by document-intelligence."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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
    jurisdiction_id: Optional[str] = None
    authority_id: Optional[str] = None
    document_type: Optional[str] = None
    effective_date: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    extensions: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
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
    parent_section_id: Optional[str] = None
    title: Optional[str] = None
    section_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
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
class ProcessingManifest:
    processing_manifest_id: str
    manifest_version: int
    document_id: str
    document_revision: int
    processing_version: str
    status: str
    provenance: Provenance
    input_bundle_manifest_ref: ManifestRef
    selected_profiles: Dict[str, str]
    reference_snapshot_set_ref: Optional[str] = None
    published_document_ref: Optional[Dict[str, Any]] = None
    published_sections_ref: Optional[Dict[str, Any]] = None
    canonical_ready_at: Optional[str] = None
    supersedes_processing_manifest_id: Optional[str] = None
    document_count: int = 0
    section_count: int = 0
    citation_count: int = 0
    failure: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
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
        return output


@dataclass(frozen=True)
class ProcessingResult:
    document: Document
    sections: List[Section]
    manifest: ProcessingManifest
    status_events: List[Dict[str, Any]]
    document_processed_event: Dict[str, Any]
