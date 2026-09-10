"""Runtime configuration helpers for local and Databricks execution."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from document_intelligence.normalize.quarantine import (
    DEFAULT_MIN_EXTRACTED_CHARS,
    DEFAULT_MIN_LEGAL_MARKERS,
    QuarantineThresholds,
)
from document_intelligence.persist.sinks import DeltaSinkConfig
from document_intelligence.persist.surfaces import (
    CANONICAL_RETRACTIONS,
    PROCESSING_MANIFESTS,
    PUBLISHED_COMMENTARY_INSIGHTS,
    PUBLISHED_DOCUMENTS,
    PUBLISHED_SECTIONS,
)


@dataclass(frozen=True)
class SurfaceUris:
    published_documents_uri: str
    published_sections_uri: str
    processing_manifests_uri: str
    published_commentary_insights_uri: str | None = None
    # The retraction ledger (ADR-0057). Optional for the same reason the commentary
    # surface is: a runtime configured with explicit per-surface URIs predates it, and
    # the *write* path never touches it — only the operator retraction job does.
    canonical_retractions_uri: str | None = None

    def to_delta_sink_config(self) -> DeltaSinkConfig:
        return DeltaSinkConfig(
            published_documents_uri=self.published_documents_uri,
            published_sections_uri=self.published_sections_uri,
            processing_manifests_uri=self.processing_manifests_uri,
            published_commentary_insights_uri=self.published_commentary_insights_uri,
        )

    @classmethod
    def from_root_uri(cls, root_uri: str) -> "SurfaceUris":
        normalized_root = root_uri.rstrip("/")
        return cls(
            published_documents_uri=_join_uri(normalized_root, PUBLISHED_DOCUMENTS.surface_name),
            published_sections_uri=_join_uri(normalized_root, PUBLISHED_SECTIONS.surface_name),
            processing_manifests_uri=_join_uri(normalized_root, PROCESSING_MANIFESTS.surface_name),
            published_commentary_insights_uri=_join_uri(
                normalized_root,
                PUBLISHED_COMMENTARY_INSIGHTS.surface_name,
            ),
            canonical_retractions_uri=_join_uri(normalized_root, CANONICAL_RETRACTIONS.surface_name),
        )


@dataclass(frozen=True)
class RuntimeSettings:
    processing_version: str
    surface_uris: SurfaceUris | None = None
    parser_backend: str = "legacy"
    enable_spacy: bool = False
    spacy_model_name: str = "xx_sent_ud_sm"
    spacy_max_chars_per_section: int = 100000
    spacy_batch_size: int = 32
    enable_llm_extractor: bool = False
    llm_confidence_threshold: float = 0.7
    enable_commentary_insights: bool = False
    commentary_insight_min_confidence: float = 0.7
    use_spark_delta: bool = False
    # ADR-0047's two text-level floors. Environment-wide defaults; a bundle's
    # `di_overrides` narrows them per source, because the honest minimum for a cantonal
    # act is not the honest minimum for a one-article communal ordinance.
    quarantine_min_extracted_chars: int = DEFAULT_MIN_EXTRACTED_CHARS
    quarantine_min_legal_markers: int = DEFAULT_MIN_LEGAL_MARKERS

    @property
    def quarantine_thresholds(self) -> QuarantineThresholds:
        return QuarantineThresholds(
            min_extracted_chars=self.quarantine_min_extracted_chars,
            min_legal_markers=self.quarantine_min_legal_markers,
        )

    @classmethod
    def from_mapping(
        cls,
        mapping: Mapping[str, str],
        *,
        processing_version: str | None = None,
        surfaces_root_uri: str | None = None,
        published_documents_uri: str | None = None,
        published_sections_uri: str | None = None,
        processing_manifests_uri: str | None = None,
        parser_backend: str | None = None,
        enable_spacy: Any | None = None,
        spacy_model_name: str | None = None,
        spacy_max_chars_per_section: Any | None = None,
        spacy_batch_size: Any | None = None,
        enable_llm_extractor: Any | None = None,
        llm_confidence_threshold: Any | None = None,
        enable_commentary_insights: Any | None = None,
        commentary_insight_min_confidence: Any | None = None,
        use_spark_delta: Any | None = None,
        quarantine_min_extracted_chars: Any | None = None,
        quarantine_min_legal_markers: Any | None = None,
    ) -> "RuntimeSettings":
        effective_processing_version = processing_version or mapping.get("DI_PROCESSING_VERSION") or "0.1.0-dev"
        effective_parser_backend = (parser_backend or mapping.get("DI_PARSER_BACKEND") or "legacy").strip()
        if effective_parser_backend not in {"legacy", "docling"}:
            raise ValueError("DI_PARSER_BACKEND must be one of: legacy, docling")
        effective_enable_spacy = (
            _coerce_bool(enable_spacy)
            if enable_spacy is not None
            else _parse_bool(mapping.get("DI_ENABLE_SPACY", "false"))
        )
        effective_spacy_model_name = (spacy_model_name or mapping.get("DI_SPACY_MODEL_NAME") or "xx_sent_ud_sm").strip()
        effective_spacy_max_chars_per_section = _coerce_int(
            spacy_max_chars_per_section
            if spacy_max_chars_per_section is not None
            else mapping.get("DI_SPACY_MAX_CHARS_PER_SECTION", "100000"),
            name="DI_SPACY_MAX_CHARS_PER_SECTION",
            minimum=1,
        )
        effective_spacy_batch_size = _coerce_int(
            spacy_batch_size if spacy_batch_size is not None else mapping.get("DI_SPACY_BATCH_SIZE", "32"),
            name="DI_SPACY_BATCH_SIZE",
            minimum=1,
        )
        effective_enable_llm_extractor = (
            _coerce_bool(enable_llm_extractor)
            if enable_llm_extractor is not None
            else _parse_bool(mapping.get("DI_ENABLE_LLM_EXTRACTOR", "false"))
        )
        effective_llm_confidence_threshold = _coerce_float(
            llm_confidence_threshold
            if llm_confidence_threshold is not None
            else mapping.get("DI_LLM_CONFIDENCE_THRESHOLD", "0.7"),
            name="DI_LLM_CONFIDENCE_THRESHOLD",
            minimum=0.0,
            maximum=1.0,
        )
        effective_enable_commentary_insights = (
            _coerce_bool(enable_commentary_insights)
            if enable_commentary_insights is not None
            else _parse_bool(mapping.get("DI_ENABLE_COMMENTARY_INSIGHTS", "false"))
        )
        effective_commentary_insight_min_confidence = _coerce_float(
            commentary_insight_min_confidence
            if commentary_insight_min_confidence is not None
            else mapping.get("DI_COMMENTARY_INSIGHT_MIN_CONFIDENCE", "0.7"),
            name="DI_COMMENTARY_INSIGHT_MIN_CONFIDENCE",
            minimum=0.0,
            maximum=1.0,
        )
        effective_use_spark_delta = (
            _coerce_bool(use_spark_delta)
            if use_spark_delta is not None
            else _parse_bool(mapping.get("DI_USE_SPARK_DELTA", "false"))
        )

        effective_quarantine_min_extracted_chars = _coerce_int(
            quarantine_min_extracted_chars
            if quarantine_min_extracted_chars is not None
            else mapping.get("DI_QUARANTINE_MIN_EXTRACTED_CHARS", str(DEFAULT_MIN_EXTRACTED_CHARS)),
            name="DI_QUARANTINE_MIN_EXTRACTED_CHARS",
            minimum=0,
        )
        effective_quarantine_min_legal_markers = _coerce_int(
            quarantine_min_legal_markers
            if quarantine_min_legal_markers is not None
            else mapping.get("DI_QUARANTINE_MIN_LEGAL_MARKERS", str(DEFAULT_MIN_LEGAL_MARKERS)),
            name="DI_QUARANTINE_MIN_LEGAL_MARKERS",
            minimum=0,
        )

        direct_documents_uri = published_documents_uri or mapping.get("DI_PUBLISHED_DOCUMENTS_URI")
        direct_sections_uri = published_sections_uri or mapping.get("DI_PUBLISHED_SECTIONS_URI")
        direct_manifests_uri = processing_manifests_uri or mapping.get("DI_PROCESSING_MANIFESTS_URI")
        direct_commentary_insights_uri = mapping.get("DI_PUBLISHED_COMMENTARY_INSIGHTS_URI")
        direct_canonical_retractions_uri = mapping.get("DI_CANONICAL_RETRACTIONS_URI")
        root_uri = surfaces_root_uri or mapping.get("DI_SURFACES_ROOT_URI")

        if any([direct_documents_uri, direct_sections_uri, direct_manifests_uri]):
            if not all([direct_documents_uri, direct_sections_uri, direct_manifests_uri]):
                raise ValueError("published surface URIs must be provided together")
            surface_uris = SurfaceUris(
                published_documents_uri=direct_documents_uri or "",
                published_sections_uri=direct_sections_uri or "",
                processing_manifests_uri=direct_manifests_uri or "",
                published_commentary_insights_uri=direct_commentary_insights_uri,
                canonical_retractions_uri=direct_canonical_retractions_uri,
            )
        elif root_uri:
            surface_uris = SurfaceUris.from_root_uri(root_uri)
        else:
            surface_uris = None

        return cls(
            processing_version=effective_processing_version,
            surface_uris=surface_uris,
            parser_backend=effective_parser_backend,
            enable_spacy=effective_enable_spacy,
            spacy_model_name=effective_spacy_model_name,
            spacy_max_chars_per_section=effective_spacy_max_chars_per_section,
            spacy_batch_size=effective_spacy_batch_size,
            enable_llm_extractor=effective_enable_llm_extractor,
            llm_confidence_threshold=effective_llm_confidence_threshold,
            enable_commentary_insights=effective_enable_commentary_insights,
            commentary_insight_min_confidence=effective_commentary_insight_min_confidence,
            use_spark_delta=effective_use_spark_delta,
            quarantine_min_extracted_chars=effective_quarantine_min_extracted_chars,
            quarantine_min_legal_markers=effective_quarantine_min_legal_markers,
        )

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None):
        return cls.from_mapping(environment or os.environ)


def _join_uri(root_uri: str, child_name: str) -> str:
    if root_uri.startswith("file://"):
        return "{root}/{child}".format(root=root_uri.rstrip("/"), child=child_name)
    if "://" in root_uri:
        return "{root}/{child}".format(root=root_uri.rstrip("/"), child=child_name)
    return os.path.join(root_uri, child_name)


def _parse_bool(raw_value: str) -> bool:
    return (raw_value or "").strip().lower() in {"1", "true", "yes", "on"}


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return _parse_bool(value)
    return bool(value)


def _coerce_int(value: Any, *, name: str, minimum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be an integer") from error
    if parsed < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return parsed


def _coerce_float(value: Any, *, name: str, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a float") from error
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return parsed
