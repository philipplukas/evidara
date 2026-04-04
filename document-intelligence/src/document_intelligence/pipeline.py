"""HTML-first bundle-based processing pipeline."""

from datetime import UTC, datetime
from typing import Any

from document_intelligence.canonical.ids import random_prefixed_id, stable_prefixed_id
from document_intelligence.canonical.models import (
    Document,
    ProcessingManifest,
    ProcessingResult,
    Section,
)
from document_intelligence.contracts.envelope import (
    ArtifactBundleAvailableEvent,
    ArtifactBundleManifest,
    ArtifactBundleManifestArtifact,
    Provenance,
)
from document_intelligence.errors import ProcessingError
from document_intelligence.events.document_processed import (
    build_document_processed_event,
)
from document_intelligence.events.status_updated import build_processing_status_event
from document_intelligence.ingest.docling_adapter import normalize_with_docling
from document_intelligence.ingest.loaders import BundleLoader, DispatchingBundleLoader
from document_intelligence.nlp.citation_extractor import extract_citations
from document_intelligence.nlp.spacy_pipeline import enrich_with_spacy
from document_intelligence.normalize.html import (
    normalize_html_document,
    normalize_plain_text_document,
)
from document_intelligence.normalize.ir import NormalizedDocumentIR
from document_intelligence.normalize.xml import normalize_xml_document
from document_intelligence.persist.sinks import CanonicalSink, InMemoryCanonicalSink
from document_intelligence.quality.invariants import validate_document_and_sections
from document_intelligence.sectionize.html import (
    SectionCandidate,
    build_sections_from_ir,
)
from document_intelligence.validate.validator import (
    validate_document,
    validate_event,
    validate_processing_manifest,
    validate_sections,
)

_DOCUMENT_TYPE_ALIASES = {
    "statute": "law",
    "act": "law",
    "gesetz": "law",
    "loi": "law",
    "legge": "law",
    "bundesgesetz": "law",
    "judgment": "decision",
    "ruling": "decision",
    "urteil": "decision",
    "arrêt": "decision",
    "sentenza": "decision",
    "entscheid": "decision",
    "beschluss": "decision",
    "kommentar": "commentary",
    "commentaire": "commentary",
    "commento": "commentary",
    "headnote": "rechtssatz",
    "legal principle": "rechtssatz",
    "leitsatz": "rechtssatz",
}


class ProcessingPipeline:
    """Minimal contract-aligned processing pipeline for the first bundle path."""

    def __init__(
        self,
        bundle_loader: BundleLoader | None = None,
        sink: CanonicalSink | None = None,
        processing_version: str = "0.1.0-dev",
        parser_backend: str = "legacy",
        enable_spacy: bool = False,
        spacy_model_name: str = "xx_sent_ud_sm",
        spacy_max_chars_per_section: int = 100000,
        spacy_batch_size: int = 32,
    ) -> None:
        if parser_backend not in {"legacy", "docling"}:
            raise ValueError("parser_backend must be one of: legacy, docling")
        self._bundle_loader = bundle_loader or DispatchingBundleLoader()
        self._sink = sink or InMemoryCanonicalSink()
        self._processing_version = processing_version
        self._parser_backend = parser_backend
        self._enable_spacy = enable_spacy
        self._spacy_model_name = spacy_model_name
        self._spacy_max_chars_per_section = spacy_max_chars_per_section
        self._spacy_batch_size = spacy_batch_size

    def process_event(self, event_data: dict[str, Any]) -> ProcessingResult:
        event = ArtifactBundleAvailableEvent.from_dict(event_data)
        selected_bundle = self._bundle_loader.load_bundle(event.payload.bundle_manifest_ref)
        primary_artifact = selected_bundle.primary_artifact
        artifact_text = self._bundle_loader.read_artifact_text(primary_artifact)

        document_id = stable_prefixed_id(
            "doc",
            selected_bundle.manifest.provenance.tenant_id,
            selected_bundle.manifest.provenance.corpus_id,
            selected_bundle.manifest.provenance.source_id,
            primary_artifact.artifact_id,
        )
        document_revision = 1
        processing_manifest_id = random_prefixed_id("pm")
        provenance = _build_canonical_provenance(
            selected_bundle.manifest.provenance,
            artifact_id=primary_artifact.artifact_id,
            document_id=document_id,
            document_revision=document_revision,
            processing_manifest_id=processing_manifest_id,
        )

        status_events = [
            build_processing_status_event(
                processing_manifest_id=processing_manifest_id,
                provenance=provenance,
                processing_version=self._processing_version,
                status="accepted",
                document_id=document_id,
                document_revision=document_revision,
                correlation_id=event.correlation_id or provenance.run_id,
                causation_id=event.event_id,
            ),
            build_processing_status_event(
                processing_manifest_id=processing_manifest_id,
                provenance=provenance,
                processing_version=self._processing_version,
                status="processing",
                document_id=document_id,
                document_revision=document_revision,
                correlation_id=event.correlation_id or provenance.run_id,
                causation_id=event.event_id,
            ),
        ]

        normalized_document = self._normalize_artifact(primary_artifact, artifact_text)
        sections = _build_sections(
            document_id=document_id,
            document_revision=document_revision,
            processing_manifest_id=processing_manifest_id,
            provenance=provenance,
            section_candidates=build_sections_from_ir(normalized_document),
        )

        document = _build_document(
            normalized_document=normalized_document,
            manifest=selected_bundle.manifest,
            primary_artifact=primary_artifact,
            provenance=provenance,
            document_id=document_id,
            document_revision=document_revision,
            processing_manifest_id=processing_manifest_id,
            processing_version=self._processing_version,
        )
        if self._enable_spacy:
            document.metadata["nlp"] = enrich_with_spacy(
                document.body_text or document.full_text,
                enabled=True,
                model_name=self._spacy_model_name,
                max_chars_per_section=self._spacy_max_chars_per_section,
                batch_size=self._spacy_batch_size,
            )

        # Citation extraction
        citations = extract_citations(document.body_text or document.full_text)
        if citations:
            document.extensions["citations"] = [c.to_dict() for c in citations]

        manifest = _build_processing_manifest(
            manifest=selected_bundle.manifest,
            provenance=provenance,
            document=document,
            sections=sections,
            processing_manifest_id=processing_manifest_id,
            processing_version=self._processing_version,
            input_bundle_manifest_id=event.payload.bundle_manifest_id,
            input_bundle_manifest_ref=event.payload.bundle_manifest_ref.to_dict(),
            normalized_document=normalized_document,
            citation_count=len(citations),
        )

        canonical_ready_event = build_processing_status_event(
            processing_manifest_id=processing_manifest_id,
            provenance=provenance,
            processing_version=self._processing_version,
            status="canonical_ready",
            document_id=document_id,
            document_revision=document_revision,
            correlation_id=event.correlation_id or provenance.run_id,
            causation_id=event.event_id,
        )
        status_events.append(canonical_ready_event)

        document_processed_event = build_document_processed_event(
            document=document,
            manifest=manifest,
            correlation_id=event.correlation_id or provenance.run_id,
            causation_id=event.event_id,
        )

        validate_document_and_sections(document, sections)
        validate_document(document)
        validate_sections(sections)
        validate_processing_manifest(manifest)
        for status_event in status_events:
            validate_event(status_event)
        validate_event(document_processed_event)

        self._sink.persist(document, sections, manifest)
        self._sink.record_status_events(status_events)
        self._sink.record_document_processed_event(document_processed_event)

        return ProcessingResult(
            document=document,
            sections=sections,
            manifest=manifest,
            status_events=status_events,
            document_processed_event=document_processed_event,
        )

    def _normalize_artifact(
        self,
        artifact: ArtifactBundleManifestArtifact,
        artifact_text: str,
    ) -> NormalizedDocumentIR:
        if self._parser_backend == "docling":
            return normalize_with_docling(
                artifact_id=artifact.artifact_id,
                artifact_text=artifact_text,
                content_type=artifact.storage_ref.content_type or "",
            )
        content_type = _normalized_content_type(artifact.storage_ref.content_type or "")
        if content_type in {"text/html", "application/xhtml+xml"}:
            return normalize_html_document(artifact_text, artifact.artifact_id)
        if content_type in {"application/xml", "text/xml"}:
            return normalize_xml_document(artifact_text, artifact.artifact_id)
        if content_type.startswith("text/plain"):
            return normalize_plain_text_document(artifact_text, artifact.artifact_id)
        raise ProcessingError(
            "unsupported_primary_artifact",
            f"unsupported primary artifact content type: {artifact.storage_ref.content_type}",
        )


_NORMALIZED_DOCUMENT_TYPES = frozenset({"law", "decision", "commentary", "rechtssatz"})
_DOCUMENT_TYPE_HINT_MAP = {"statute": "law"}


def _resolve_document_type(
    extracted: str | None,
    hint: str | None,
) -> str | None:
    candidate = extracted or hint
    if candidate is None:
        return None
    mapped = _DOCUMENT_TYPE_HINT_MAP.get(candidate, candidate)
    if mapped in _NORMALIZED_DOCUMENT_TYPES:
        return mapped
    return None


def _build_document(
    *,
    normalized_document: NormalizedDocumentIR,
    manifest: ArtifactBundleManifest,
    primary_artifact: ArtifactBundleManifestArtifact,
    provenance: Provenance,
    document_id: str,
    document_revision: int,
    processing_manifest_id: str,
    processing_version: str,
) -> Document:
    now = _utc_now()
    metadata = {
        "normalizer": normalized_document.metadata.get("normalizer"),
        "source_origin_kind": manifest.source_origin_kind,
        "trust_tier": manifest.trust_tier,
        "source_defaults": dict(manifest.source_defaults),
    }
    extracted_metadata = dict(normalized_document.metadata.get("extracted_metadata") or {})
    if extracted_metadata:
        metadata["extracted_metadata"] = extracted_metadata
    source_flavor = normalized_document.metadata.get("source_flavor")
    if source_flavor:
        metadata["source_flavor"] = source_flavor
    docling_metadata = normalized_document.metadata.get("docling")
    if docling_metadata:
        metadata["docling"] = dict(docling_metadata)

    return Document(
        document_id=document_id,
        document_revision=document_revision,
        processing_manifest_id=processing_manifest_id,
        provenance=provenance,
        primary_artifact_id=primary_artifact.artifact_id,
        jurisdiction_id=manifest.source_defaults.get("jurisdiction_id"),
        authority_id=manifest.source_defaults.get("authority_id"),
        title=_choose_document_title(normalized_document),
        processed_at=now,
        processing_version=processing_version,
        lifecycle_status="active",
        full_text=normalized_document.full_text,
        body_text=normalized_document.body_text,
        document_type=_resolve_document_type(
            normalized_document.metadata.get("document_type"),
            manifest.source_defaults.get("document_type_hint"),
        ),
        metadata=metadata,
        extensions={},
    )


def _build_sections(
    *,
    document_id: str,
    document_revision: int,
    processing_manifest_id: str,
    provenance: Provenance,
    section_candidates: list[SectionCandidate],
) -> list[Section]:
    sections: list[Section] = []
    for ordinal, candidate in enumerate(section_candidates):
        sections.append(
            Section(
                section_id=stable_prefixed_id("sec", document_id, str(document_revision), str(ordinal)),
                document_id=document_id,
                document_revision=document_revision,
                processing_manifest_id=processing_manifest_id,
                provenance=provenance,
                parent_section_id=None,
                ordinal=ordinal,
                depth=candidate.depth,
                title=candidate.title,
                content=candidate.content,
                section_type=candidate.section_type,
                metadata=dict(candidate.metadata),
            )
        )
    return sections


def _build_processing_manifest(
    *,
    manifest: ArtifactBundleManifest,
    provenance: Provenance,
    document: Document,
    sections: list[Section],
    processing_manifest_id: str,
    processing_version: str,
    input_bundle_manifest_id: str,
    input_bundle_manifest_ref: dict[str, Any],
    normalized_document: NormalizedDocumentIR,
    citation_count: int = 0,
) -> ProcessingManifest:
    published_document_ref = {
        "surface_name": "published_documents",
        "surface_version": 1,
        "record_key": {
            "document_id": document.document_id,
            "processing_manifest_id": processing_manifest_id,
        },
    }
    published_sections_ref = {
        "surface_name": "published_sections",
        "surface_version": 1,
        "record_filter": {
            "document_id": document.document_id,
            "processing_manifest_id": processing_manifest_id,
        },
    }
    selected_profiles = {
        "source_profile_ref": manifest.di_overrides.get(
            "source_profile_ref",
            normalized_document.metadata.get("source_profile_ref", "default_html_v1"),
        ),
        "jurisdiction_profile_ref": manifest.di_overrides.get("jurisdiction_profile_ref", "default_jurisdiction_v1"),
        "resolution_policy_ref": manifest.di_overrides.get("resolution_policy_ref", "default_resolution_v1"),
    }
    normalization_profile_ref = manifest.di_overrides.get(
        "normalization_profile_ref",
        normalized_document.metadata.get("normalization_profile_ref"),
    )
    if normalization_profile_ref:
        selected_profiles["normalization_profile_ref"] = normalization_profile_ref

    return ProcessingManifest(
        processing_manifest_id=processing_manifest_id,
        manifest_version=1,
        document_id=document.document_id,
        document_revision=document.document_revision,
        processing_version=processing_version,
        status="canonical_ready",
        provenance=provenance,
        input_bundle_manifest_ref=_manifest_ref_from_dict(input_bundle_manifest_ref),
        selected_profiles=selected_profiles,
        reference_snapshot_set_ref=manifest.reference_context.get("reference_snapshot_set_ref"),
        published_document_ref=published_document_ref,
        published_sections_ref=published_sections_ref,
        canonical_ready_at=_utc_now(),
        supersedes_processing_manifest_id=None,
        document_count=1,
        section_count=len(sections),
        citation_count=citation_count,
        failure=None,
    )


def _manifest_ref_from_dict(data: dict[str, Any]):
    from document_intelligence.contracts.envelope import ManifestRef

    return ManifestRef.from_dict(data)


def _build_canonical_provenance(
    provenance: Provenance,
    *,
    artifact_id: str,
    document_id: str,
    document_revision: int,
    processing_manifest_id: str,
) -> Provenance:
    return provenance.with_updates(
        artifact_id=artifact_id,
        document_id=document_id,
        document_revision=document_revision,
        processing_manifest_id=processing_manifest_id,
    )


def _choose_document_title(normalized_document: NormalizedDocumentIR) -> str:
    if normalized_document.title:
        return normalized_document.title
    for block in normalized_document.blocks:
        if block.type == "heading":
            return block.text
    return "Untitled document"


def _normalized_content_type(content_type: str) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def _normalize_document_type(document_type: str | None) -> str | None:
    if document_type is None:
        return None
    normalized = document_type.strip().lower()
    if not normalized:
        return None
    return _DOCUMENT_TYPE_ALIASES.get(normalized, normalized)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
