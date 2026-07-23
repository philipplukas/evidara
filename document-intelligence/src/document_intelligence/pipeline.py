"""HTML-first bundle-based processing pipeline."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Literal

from document_intelligence.canonical.ids import random_prefixed_id, stable_prefixed_id
from document_intelligence.canonical.jurisdiction import resolve_jurisdiction_from_manifest
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
from document_intelligence.enrichment.commentary_insights import extract_commentary_insights
from document_intelligence.errors import ProcessingError
from document_intelligence.events.document_processed import (
    build_document_processed_event,
)
from document_intelligence.events.status_updated import build_processing_status_event
from document_intelligence.extractors.extraction_hints import extraction_hints_from_bundle_metadata
from document_intelligence.extractors.metadata import (
    FieldProvenanceAudit,
    MetadataExtractionCandidate,
    MetadataExtractor,
    SourceTier,
)
from document_intelligence.ingest.docling_adapter import normalize_with_docling
from document_intelligence.ingest.loaders import (
    BundleLoader,
    DispatchingBundleLoader,
    SelectedArtifactBundle,
)
from document_intelligence.nlp.citation_extractor import extract_citations, normalize_citation
from document_intelligence.nlp.spacy_pipeline import enrich_with_spacy
from document_intelligence.normalize.html import (
    normalize_html_document,
    normalize_markdown_document,
    normalize_plain_text_document,
)
from document_intelligence.normalize.ir import NormalizedDocumentIR
from document_intelligence.normalize.pdf import normalize_pdf_document
from document_intelligence.normalize.titles import is_placeholder_title
from document_intelligence.normalize.xml import normalize_xml_document
from document_intelligence.persist.sinks import CanonicalSink, InMemoryCanonicalSink
from document_intelligence.persist.surfaces import PUBLISHED_DOCUMENTS, PUBLISHED_SECTIONS
from document_intelligence.profiles.registry import resolve_selected_profiles
from document_intelligence.quality.invariants import validate_document_and_sections
from document_intelligence.sectionize.html import (
    SectionCandidate,
    build_sections_from_ir,
)
from document_intelligence.validate.validator import (
    validate_commentary_insights,
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


def _document_identity_key(bundle: SelectedArtifactBundle) -> str:
    """The stable per-document component of ``document_id`` (#652).

    ``upstream_locator`` is the document's permalink at the authority — an ELI for
    Fedlex (``https://fedlex.data.admin.ch/eli/cc/1999/404``), the AS landing page
    for a communal ordinance. It identifies *the law*, so re-acquiring it yields
    another **revision** of the same document, which is what the surface and
    ``_pick_latest_row`` were always built for.

    This used to key on ``primary_artifact.artifact_id``, a per-run ULID. That
    minted a brand-new document on every acquisition run, so the index accumulated
    a fresh copy of the same law each time it was fetched — and pipeline fixes
    never reached the already-indexed copies, because they were different
    documents rather than superseded revisions (#652).

    Falls back to the artifact id when a source publishes no stable locator: that
    preserves the old behaviour for those sources rather than collapsing genuinely
    distinct documents onto one id, which would be the worse failure.
    """
    locator = (bundle.manifest.upstream_locator or "").strip()
    return locator or bundle.primary_artifact.artifact_id


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
        enable_llm_extractor: bool = False,
        llm_confidence_threshold: float = 0.7,
        llm_metadata_extractor: MetadataExtractor | None = None,
        enable_commentary_insights: bool = False,
        commentary_insight_min_confidence: float = 0.7,
    ) -> None:
        if parser_backend not in {"legacy", "docling"}:
            raise ValueError("parser_backend must be one of: legacy, docling")
        if not 0.0 <= llm_confidence_threshold <= 1.0:
            raise ValueError("llm_confidence_threshold must be between 0.0 and 1.0")
        if not 0.0 <= commentary_insight_min_confidence <= 1.0:
            raise ValueError("commentary_insight_min_confidence must be between 0.0 and 1.0")
        self._bundle_loader = bundle_loader or DispatchingBundleLoader()
        self._sink = sink or InMemoryCanonicalSink()
        self._processing_version = processing_version
        self._parser_backend = parser_backend
        self._enable_spacy = enable_spacy
        self._spacy_model_name = spacy_model_name
        self._spacy_max_chars_per_section = spacy_max_chars_per_section
        self._spacy_batch_size = spacy_batch_size
        self._enable_llm_extractor = enable_llm_extractor
        self._llm_confidence_threshold = llm_confidence_threshold
        self._llm_metadata_extractor = llm_metadata_extractor
        self._enable_commentary_insights = enable_commentary_insights
        self._commentary_insight_min_confidence = commentary_insight_min_confidence

    def process_event(self, event_data: dict[str, Any]) -> ProcessingResult:
        event = ArtifactBundleAvailableEvent.from_dict(event_data)
        selected_bundle = self._bundle_loader.load_bundle(event.payload.bundle_manifest_ref)
        primary_artifact = selected_bundle.primary_artifact
        # Binary modalities (PDF, #590) are read as raw bytes and normalised layout-aware;
        # text modalities keep the existing decode-then-normalise path. Reading a PDF as
        # text would corrupt it, and normalising the corrupted text would silently splice
        # marginal headings mid-sentence — the exact failure #590 exists to prevent.
        primary_content_type = _normalized_content_type(primary_artifact.storage_ref.content_type or "")
        artifact_text: str | None = None
        if primary_content_type == "application/pdf":
            pdf_bytes = self._bundle_loader.read_artifact_bytes(primary_artifact)
        else:
            artifact_text = self._bundle_loader.read_artifact_text(primary_artifact)

        document_id = stable_prefixed_id(
            "doc",
            selected_bundle.manifest.provenance.tenant_id,
            selected_bundle.manifest.provenance.corpus_id,
            selected_bundle.manifest.provenance.source_id,
            _document_identity_key(selected_bundle),
        )
        # Re-acquiring a law publishes the *next* revision of it, not another copy pinned at
        # 1 (#652). Keying `document_id` on the upstream locator made re-acquisitions land on
        # the same document; this is what makes them ordered once they do. Without it,
        # `_pick_latest_row` falls back to comparing `processed_at` strings and legal-search's
        # stale-event guard (`document_revision < latest`) can never fire, so a redelivered or
        # replayed older event silently overwrites newer content.
        #
        # `None` means the sink has no history for this document — new document, or a sink that
        # cannot read back — and publication starts at 1, exactly as before.
        previous_revision = self._sink.latest_document_revision(document_id)
        document_revision = (previous_revision or 0) + 1
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

        if primary_content_type == "application/pdf":
            # PDFs always normalise geometrically (ADR-0041); ``parser_backend`` selects
            # between legacy and docling for *text* modalities only. Deliberately not
            # configurable: a text-order extractor splices marginal headings into body
            # sentences, and no environment variable should be able to silently select
            # silently-corrupted legal text.
            normalized_document = normalize_pdf_document(pdf_bytes, primary_artifact.artifact_id)
        else:
            assert artifact_text is not None  # guaranteed by the content-type branch above
            normalized_document = self._normalize_artifact(primary_artifact, artifact_text)
        normalized_document = _merge_extraction_hints_into_ir(
            selected_bundle.manifest,
            normalized_document,
        )
        sections = _build_sections(
            document_id=document_id,
            document_revision=document_revision,
            processing_manifest_id=processing_manifest_id,
            provenance=provenance,
            section_candidates=build_sections_from_ir(normalized_document),
        )
        llm_metadata = self._extract_metadata_candidate(
            normalized_document=normalized_document,
            manifest=selected_bundle.manifest,
            primary_artifact=primary_artifact,
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
            llm_metadata=llm_metadata,
            llm_confidence_threshold=self._llm_confidence_threshold,
            llm_extractor_enabled=self._enable_llm_extractor,
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
            citation_dicts = []
            for c in citations:
                d = c.to_dict()
                normalized = normalize_citation(c)
                if normalized:
                    d["normalized_reference"] = normalized
                citation_dicts.append(d)
            document.extensions["citations"] = citation_dicts

        commentary_insights = []
        if self._enable_commentary_insights and _should_extract_commentary_insights(
            document=document,
            manifest=selected_bundle.manifest,
            normalized_document=normalized_document,
        ):
            commentary_insights = extract_commentary_insights(
                document=document,
                sections=sections,
                min_confidence=self._commentary_insight_min_confidence,
            )
        if self._enable_commentary_insights:
            document.metadata["commentary_insights"] = {
                "enabled": True,
                "emitted_count": len(commentary_insights),
                "min_confidence": self._commentary_insight_min_confidence,
            }

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
        validate_commentary_insights(commentary_insights)
        validate_processing_manifest(manifest)
        for status_event in status_events:
            validate_event(status_event)
        validate_event(document_processed_event)

        self._sink.persist(document, sections, manifest)
        self._sink.persist_commentary_insights(commentary_insights)
        self._sink.record_status_events(status_events)
        self._sink.record_document_processed_event(document_processed_event)

        return ProcessingResult(
            document=document,
            sections=sections,
            commentary_insights=commentary_insights,
            manifest=manifest,
            status_events=status_events,
            document_processed_event=document_processed_event,
        )

    def _extract_metadata_candidate(
        self,
        *,
        normalized_document: NormalizedDocumentIR,
        manifest: ArtifactBundleManifest,
        primary_artifact: ArtifactBundleManifestArtifact,
    ) -> MetadataExtractionCandidate | None:
        if not self._enable_llm_extractor or self._llm_metadata_extractor is None:
            return None
        if not _needs_llm_extraction(normalized_document, manifest):
            return MetadataExtractionCandidate(
                confidence=1.0,
                summary="skipped_structured_sufficient",
                raw={"reason": "title and document_type already resolved from structured extraction"},
            )
        try:
            return self._llm_metadata_extractor.extract(
                normalized_document=normalized_document,
                manifest=manifest,
                primary_artifact=primary_artifact,
            )
        except Exception as error:
            return MetadataExtractionCandidate(
                confidence=0.0,
                summary=f"extractor_failed:{type(error).__name__}",
                raw={"error": str(error)},
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
        if content_type in {"text/markdown", "text/x-markdown", "application/markdown"}:
            return normalize_markdown_document(artifact_text, artifact.artifact_id)
        if content_type in {"application/json", "application/ld+json", "text/json"}:
            return normalize_plain_text_document(artifact_text, artifact.artifact_id)
        if content_type.startswith("text/plain"):
            detected = _detect_text_modality(artifact_text)
            if detected == "html":
                return normalize_html_document(artifact_text, artifact.artifact_id)
            if detected == "xml":
                return normalize_xml_document(artifact_text, artifact.artifact_id)
            if detected == "markdown":
                return normalize_markdown_document(artifact_text, artifact.artifact_id)
            return normalize_plain_text_document(artifact_text, artifact.artifact_id)
        detected = _detect_text_modality(artifact_text)
        if detected == "html":
            return normalize_html_document(artifact_text, artifact.artifact_id)
        if detected == "xml":
            return normalize_xml_document(artifact_text, artifact.artifact_id)
        if detected == "markdown":
            return normalize_markdown_document(artifact_text, artifact.artifact_id)
        raise ProcessingError(
            "unsupported_primary_artifact",
            f"unsupported primary artifact content type: {artifact.storage_ref.content_type}",
        )


_NORMALIZED_DOCUMENT_TYPES = frozenset({"law", "decision", "commentary", "rechtssatz"})
_DOCUMENT_TYPE_HINT_MAP = {"statute": "law", "judgment": "decision"}
# Labels sometimes present in extracted metadata (normalized by lowercasing for lookup).
_EXTRACTED_DOCUMENT_TYPE_LABELS = {"urteil": "decision"}


def _normalize_document_type_token(raw: str) -> str | None:
    s = raw.strip()
    if not s:
        return None
    if s in _DOCUMENT_TYPE_HINT_MAP:
        return _DOCUMENT_TYPE_HINT_MAP[s]
    lowered = s.lower()
    if lowered in _EXTRACTED_DOCUMENT_TYPE_LABELS:
        return _EXTRACTED_DOCUMENT_TYPE_LABELS[lowered]
    if s in _NORMALIZED_DOCUMENT_TYPES:
        return s
    return None


def _resolve_document_type(
    extracted: str | None,
    hint: str | None,
) -> str | None:
    if extracted is not None:
        resolved = _normalize_document_type_token(extracted)
        if resolved is not None:
            return resolved
    if hint is not None:
        return _normalize_document_type_token(hint)
    return None


def _merge_extraction_hints_into_ir(
    manifest: ArtifactBundleManifest,
    normalized_document: NormalizedDocumentIR,
) -> NormalizedDocumentIR:
    """Attach v1 ``extraction_hints`` from bundle_metadata onto normalized IR metadata."""
    hints = extraction_hints_from_bundle_metadata(dict(manifest.bundle_metadata or {}))
    if not hints:
        return normalized_document
    new_meta = dict(normalized_document.metadata)
    new_meta["extraction_hints"] = hints
    return replace(normalized_document, metadata=new_meta)


def _is_placeholder_title(title: str | None) -> bool:
    # Delegates to the shared predicate: this list and the two in
    # `ingest.docling_adapter` and platform-control had drifted, and the gap is what
    # let a leaked filename outrank a correct acquisition hint (#771).
    return is_placeholder_title(title)


def _effective_title_from_normalized(
    normalized_document: NormalizedDocumentIR,
) -> tuple[str, Literal["structured", "manifest", "heuristic"]]:
    """Resolve display title: structured body, then acquisition hints, then headings."""
    hints = normalized_document.metadata.get("extraction_hints")
    hint_title: str | None = None
    if isinstance(hints, dict):
        raw = hints.get("title_hint")
        if isinstance(raw, str) and raw.strip():
            hint_title = raw.strip()
            if _is_placeholder_title(hint_title):
                hint_title = None

    structured = normalized_document.metadata.get("title")
    if isinstance(structured, str):
        structured = structured.strip() or None

    if hint_title and _is_placeholder_title(structured):
        return hint_title, "manifest"
    if structured and not _is_placeholder_title(structured):
        return structured, "structured"
    if hint_title:
        return hint_title, "manifest"
    for block in normalized_document.blocks:
        if block.type == "heading":
            return block.text, "structured"
    return "Untitled document", "heuristic"


def _compute_llm_invoked(
    llm_metadata: MetadataExtractionCandidate | None,
    *,
    llm_extractor_enabled: bool,
) -> bool:
    """True when the configured extractor's ``extract()`` ran (not pre-skipped)."""
    if not llm_extractor_enabled or llm_metadata is None:
        return False
    summary = (llm_metadata.summary or "").strip()
    if summary == "skipped_structured_sufficient":
        return False
    return True


def _resolve_in_force_window(
    hints: Any,
    extracted_metadata: dict[str, Any],
) -> dict[str, tuple[str, SourceTier]]:
    """Resolve `{field: (value, provenance_source)}` for the in-force window.

    Two independent sources can establish it, in precedence order:

    1. ``extraction_hints`` from acquisition (``manifest``) — authoritative,
       because the provider read it from the publisher's own structured
       metadata (Fedlex ``jolux`` applicability dates, ``gemeinde_http``
       ``inkrafttretendatum``, RIS ``Inkrafttretensdatum``).
    2. The normalizer's ``extracted_metadata`` (``structured``) — for RIS, the
       ``ct="ikra"``/``ct="akra"`` fields in the document XML itself, already
       reformatted to ISO by the XML normalizer.

    Values are passed through as-is (hints are already sanitized to non-empty
    strings by ``coerce_extraction_hints``). Returns only the fields that were
    actually established: nothing is parsed, inferred or defaulted here, because
    a wrong date is worse than a missing one — a missing window must stay
    missing so the four-valued in-force model can answer ``unknown`` instead of
    being handed a guess (ADR-0033).
    """
    window: dict[str, tuple[str, SourceTier]] = {}
    hints_dict = hints if isinstance(hints, dict) else {}
    for field_name, hint_key in (
        ("in_force_from", "in_force_from_hint"),
        ("in_force_until", "in_force_until_hint"),
    ):
        hinted = hints_dict.get(hint_key)
        if isinstance(hinted, str) and hinted.strip():
            window[field_name] = (hinted.strip(), "manifest")
            continue
        extracted = extracted_metadata.get(field_name)
        if isinstance(extracted, str) and extracted.strip():
            window[field_name] = (extracted.strip(), "structured")
    return window


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
    llm_metadata: MetadataExtractionCandidate | None,
    llm_confidence_threshold: float,
    llm_extractor_enabled: bool,
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
    eh = normalized_document.metadata.get("extraction_hints")
    if isinstance(eh, dict) and eh:
        metadata["extraction_hints"] = dict(eh)
    # Temporal validity (#628/#633, extended to AT RIS by #663): promote the
    # in-force window onto the document's own metadata. The search projection
    # already reads `metadata.in_force_from` / `metadata.in_force_until`, so
    # this is the hop that lets four-valued in-force logic answer instead of
    # reporting `unknown`. Only set when it was actually established upstream —
    # an absent window stays absent rather than being inferred from a nearby date.
    in_force_window = _resolve_in_force_window(eh, extracted_metadata)
    for field_name, (value, _source) in in_force_window.items():
        metadata[field_name] = value
    official_citation = _resolve_official_citation(normalized_document.metadata, extracted_metadata, eh)
    if official_citation:
        metadata["official_citation"] = official_citation
    original_language = _resolve_original_language(normalized_document.metadata, manifest.source_defaults)
    if original_language:
        metadata["original_language"] = original_language
        metadata["translation_status"] = "original"
    source_flavor = normalized_document.metadata.get("source_flavor")
    if source_flavor:
        metadata["source_flavor"] = source_flavor
    if "html_parse_used_fallback" in normalized_document.metadata:
        metadata["html_parse_used_fallback"] = normalized_document.metadata["html_parse_used_fallback"]
    html_parse_recovery = normalized_document.metadata.get("html_parse_recovery")
    if html_parse_recovery:
        metadata["html_parse_recovery"] = html_parse_recovery
    docling_metadata = normalized_document.metadata.get("docling")
    if docling_metadata:
        metadata["docling"] = dict(docling_metadata)
    applied_llm_metadata = bool(
        llm_metadata
        and llm_metadata.confidence >= llm_confidence_threshold
        and (llm_metadata.title or llm_metadata.document_type)
    )
    if llm_extractor_enabled:
        if llm_metadata is None:
            metadata["llm_extraction"] = {
                "enabled": True,
                "applied": False,
                "summary": "no_extractor_configured",
                "confidence_threshold": llm_confidence_threshold,
                "llm_invoked": False,
            }
        else:
            metadata["llm_extraction"] = llm_metadata.to_metadata(applied=applied_llm_metadata)
            metadata["llm_extraction"]["confidence_threshold"] = llm_confidence_threshold
            metadata["llm_extraction"]["llm_invoked"] = _compute_llm_invoked(
                llm_metadata,
                llm_extractor_enabled=llm_extractor_enabled,
            )
    provenance_audit = FieldProvenanceAudit()

    title, title_tier = _effective_title_from_normalized(normalized_document)
    title_source: Literal["structured", "manifest", "heuristic", "llm"] = title_tier
    if applied_llm_metadata and llm_metadata and llm_metadata.title:
        title = llm_metadata.title.strip() or title
        title_source = "llm"
    provenance_audit.set("title", title, title_source)  # type: ignore[arg-type]

    llm_document_type = None
    if applied_llm_metadata and llm_metadata:
        llm_document_type = _normalize_document_type(llm_metadata.document_type)

    eh_for_type = normalized_document.metadata.get("extraction_hints")
    eh_doc_hint = (
        eh_for_type.get("document_type_hint")
        if isinstance(eh_for_type, dict) and isinstance(eh_for_type.get("document_type_hint"), str)
        else None
    )
    merged_type_hint = eh_doc_hint or manifest.source_defaults.get("document_type_hint")
    resolved_doc_type = _resolve_document_type(
        llm_document_type or normalized_document.metadata.get("document_type"),
        merged_type_hint,
    )
    if llm_document_type and resolved_doc_type == llm_document_type:
        conf = llm_metadata.confidence if llm_metadata else 0.0
        provenance_audit.set("document_type", resolved_doc_type, "llm", conf)
    elif normalized_document.metadata.get("document_type"):
        provenance_audit.set("document_type", resolved_doc_type, "structured")
    elif eh_doc_hint:
        provenance_audit.set("document_type", resolved_doc_type, "manifest")
    elif manifest.source_defaults.get("document_type_hint"):
        provenance_audit.set("document_type", resolved_doc_type, "manifest")

    source_family = normalized_document.metadata.get("source_family")
    if source_family:
        provenance_audit.set("source_family", source_family, "structured")
    elif llm_metadata and llm_metadata.document_type and applied_llm_metadata:
        provenance_audit.set("source_family", llm_metadata.document_type, "llm", llm_metadata.confidence)

    for field_name in ("court_name", "decision_date", "ecli", "geschaeftszahl", "publication_organ"):
        val = extracted_metadata.get(field_name)
        if val:
            provenance_audit.set(field_name, val, "structured")

    # The source is carried through rather than hardcoded to "manifest": once the
    # XML fallback can establish the window, labelling it "manifest" would be a
    # provenance lie about where the date actually came from.
    for field_name, (value, source) in in_force_window.items():
        provenance_audit.set(field_name, value, source)

    metadata["field_provenance"] = provenance_audit.to_dict()

    return Document(
        document_id=document_id,
        document_revision=document_revision,
        processing_manifest_id=processing_manifest_id,
        provenance=provenance,
        primary_artifact_id=primary_artifact.artifact_id,
        jurisdiction_id=resolve_jurisdiction_from_manifest(
            manifest.source_defaults,
            manifest.reference_context,
        ),
        authority_id=manifest.source_defaults.get("authority_id"),
        title=title,
        processed_at=now,
        processing_version=processing_version,
        lifecycle_status="active",
        full_text=normalized_document.full_text,
        body_text=normalized_document.body_text,
        document_type=resolved_doc_type,
        metadata=metadata,
        extensions={},
    )


def _resolve_official_citation(
    normalized_metadata: dict[str, Any],
    extracted_metadata: dict[str, Any],
    hints: Any = None,
) -> str | None:
    """Resolve the citation a reader would use to look this document up.

    Three sources, in precedence order:

    1. An explicit ``official_citation`` on the normalized document.
    2. The publication organ from structured metadata (AT ``kundmachungsorgan``,
       e.g. ``BGBl. II Nr. 219/2026``).
    3. ``official_citation_hint`` from acquisition — the legislative identifier
       the provider read off the publisher's own payload (#755).

    The hint ranks last deliberately: it is a bare systematic number, so a
    richer citation already on the document should win. But it must rank above
    ``None``, because for Swiss legislation it is the *only* source. The number
    appears in the running header of the source PDF, and page-furniture removal
    strips exactly that — so a statute ends up unfindable by its own citation
    while the value sat in acquisition metadata all along.
    """
    explicit = normalized_metadata.get("official_citation")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()

    for field_name in ("publication_organ", "kundmachungsorgan"):
        candidate = extracted_metadata.get(field_name)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    if isinstance(hints, dict):
        hinted = hints.get("official_citation_hint")
        if isinstance(hinted, str) and hinted.strip():
            return hinted.strip()

    return None


def _resolve_original_language(
    normalized_metadata: dict[str, Any],
    source_defaults: dict[str, Any],
) -> str | None:
    explicit = normalized_metadata.get("language")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip().split("-")[0].lower()

    default_languages = source_defaults.get("language_codes")
    if isinstance(default_languages, list):
        for candidate in default_languages:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip().split("-")[0].lower()

    return None


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
        section_metadata = dict(candidate.metadata)
        section_citations = extract_citations(candidate.content)
        if section_citations:
            section_citation_dicts = []
            for c in section_citations:
                d = c.to_dict()
                normalized = normalize_citation(c)
                if normalized:
                    d["normalized_reference"] = normalized
                section_citation_dicts.append(d)
            section_metadata["citations"] = section_citation_dicts
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
                metadata=section_metadata,
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
    published_document_ref = PUBLISHED_DOCUMENTS.dataset_ref(
        document_id=document.document_id,
        processing_manifest_id=processing_manifest_id,
    )
    published_sections_ref = PUBLISHED_SECTIONS.dataset_ref(
        document_id=document.document_id,
        processing_manifest_id=processing_manifest_id,
    )
    selected_profiles = resolve_selected_profiles(
        source_origin_kind=manifest.source_origin_kind,
        trust_tier=manifest.trust_tier,
        source_defaults=manifest.source_defaults,
        di_overrides=manifest.di_overrides,
        normalized_metadata=normalized_document.metadata,
    )

    return ProcessingManifest(
        processing_manifest_id=processing_manifest_id,
        manifest_version=1,
        document_id=document.document_id,
        document_revision=document.document_revision,
        processing_version=processing_version,
        status="canonical_ready",
        provenance=provenance,
        input_bundle_manifest_ref=_manifest_ref_from_dict(input_bundle_manifest_ref),
        selected_profiles=selected_profiles.to_dict(),
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
    """Backward-compatible title resolution; prefer :func:`_effective_title_from_normalized`."""
    title, _tier = _effective_title_from_normalized(normalized_document)
    return title


def _needs_llm_extraction(
    normalized_document: NormalizedDocumentIR,
    manifest: ArtifactBundleManifest,
) -> bool:
    """Return True when structured extraction left gaps that an LLM should fill."""
    md = normalized_document.metadata
    hints = md.get("extraction_hints") if isinstance(md.get("extraction_hints"), dict) else {}
    title_resolved, _tier = _effective_title_from_normalized(normalized_document)
    has_title = bool(title_resolved) and title_resolved != "Untitled document"
    hint_doc_type = hints.get("document_type_hint") if isinstance(hints.get("document_type_hint"), str) else None
    has_doc_type = bool(
        md.get("document_type")
        or md.get("source_family")
        or manifest.source_defaults.get("document_type_hint")
        or (hint_doc_type and hint_doc_type.strip())
    )
    return not (has_title and has_doc_type)


def _should_extract_commentary_insights(
    *,
    document: Document,
    manifest: ArtifactBundleManifest,
    normalized_document: NormalizedDocumentIR,
) -> bool:
    if document.document_type == "commentary":
        return True
    hint = manifest.source_defaults.get("document_type_hint")
    if isinstance(hint, str) and _normalize_document_type_token(hint) == "commentary":
        return True
    hints = normalized_document.metadata.get("extraction_hints")
    if isinstance(hints, dict):
        hint = hints.get("document_type_hint")
        if isinstance(hint, str) and _normalize_document_type_token(hint) == "commentary":
            return True
    source_family = normalized_document.metadata.get("source_family")
    return isinstance(source_family, str) and _normalize_document_type_token(source_family) == "commentary"


def _normalized_content_type(content_type: str) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def _detect_text_modality(text: str) -> str | None:
    snippet = text.lstrip()[:500].lower()
    if not snippet:
        return None
    if snippet.startswith("<!doctype html") or "<html" in snippet or "<body" in snippet:
        return "html"
    if snippet.startswith("<?xml") or snippet.startswith("<dokument") or snippet.startswith("<article"):
        return "xml"
    if snippet.startswith("#") or "\n#" in snippet or "\n- " in snippet or "\n* " in snippet:
        return "markdown"
    return None


def _normalize_document_type(document_type: str | None) -> str | None:
    if document_type is None:
        return None
    normalized = document_type.strip().lower()
    if not normalized:
        return None
    return _DOCUMENT_TYPE_ALIASES.get(normalized, normalized)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
