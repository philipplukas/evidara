"""Runtime configuration helpers for local and Databricks execution."""

import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from document_intelligence.persist.sinks import DeltaSinkConfig
from document_intelligence.persist.surfaces import (
    PROCESSING_MANIFESTS,
    PUBLISHED_DOCUMENTS,
    PUBLISHED_SECTIONS,
)


@dataclass(frozen=True)
class SurfaceUris:
    published_documents_uri: str
    published_sections_uri: str
    processing_manifests_uri: str

    def to_delta_sink_config(self) -> DeltaSinkConfig:
        return DeltaSinkConfig(
            published_documents_uri=self.published_documents_uri,
            published_sections_uri=self.published_sections_uri,
            processing_manifests_uri=self.processing_manifests_uri,
        )

    @classmethod
    def from_root_uri(cls, root_uri: str) -> "SurfaceUris":
        normalized_root = root_uri.rstrip("/")
        return cls(
            published_documents_uri=_join_uri(
                normalized_root, PUBLISHED_DOCUMENTS.surface_name
            ),
            published_sections_uri=_join_uri(
                normalized_root, PUBLISHED_SECTIONS.surface_name
            ),
            processing_manifests_uri=_join_uri(
                normalized_root, PROCESSING_MANIFESTS.surface_name
            ),
        )


@dataclass(frozen=True)
class RuntimeSettings:
    processing_version: str
    surface_uris: Optional[SurfaceUris] = None
    parser_backend: str = "legacy"
    enable_spacy: bool = False
    spacy_model_name: str = "xx_sent_ud_sm"
    spacy_max_chars_per_section: int = 100000
    spacy_batch_size: int = 32

    @classmethod
    def from_mapping(
        cls,
        mapping: Mapping[str, str],
        *,
        processing_version: Optional[str] = None,
        surfaces_root_uri: Optional[str] = None,
        published_documents_uri: Optional[str] = None,
        published_sections_uri: Optional[str] = None,
        processing_manifests_uri: Optional[str] = None,
        parser_backend: Optional[str] = None,
        enable_spacy: Optional[Any] = None,
        spacy_model_name: Optional[str] = None,
        spacy_max_chars_per_section: Optional[Any] = None,
        spacy_batch_size: Optional[Any] = None,
    ) -> "RuntimeSettings":
        effective_processing_version = (
            processing_version
            or mapping.get("DI_PROCESSING_VERSION")
            or "0.1.0-dev"
        )
        effective_parser_backend = (
            parser_backend or mapping.get("DI_PARSER_BACKEND") or "legacy"
        ).strip()
        if effective_parser_backend not in {"legacy", "docling"}:
            raise ValueError("DI_PARSER_BACKEND must be one of: legacy, docling")
        effective_enable_spacy = (
            _coerce_bool(enable_spacy)
            if enable_spacy is not None
            else _parse_bool(mapping.get("DI_ENABLE_SPACY", "false"))
        )
        effective_spacy_model_name = (
            (spacy_model_name or mapping.get("DI_SPACY_MODEL_NAME") or "xx_sent_ud_sm").strip()
        )
        effective_spacy_max_chars_per_section = _coerce_int(
            spacy_max_chars_per_section
            if spacy_max_chars_per_section is not None
            else mapping.get("DI_SPACY_MAX_CHARS_PER_SECTION", "100000"),
            name="DI_SPACY_MAX_CHARS_PER_SECTION",
            minimum=1,
        )
        effective_spacy_batch_size = _coerce_int(
            spacy_batch_size
            if spacy_batch_size is not None
            else mapping.get("DI_SPACY_BATCH_SIZE", "32"),
            name="DI_SPACY_BATCH_SIZE",
            minimum=1,
        )

        direct_documents_uri = (
            published_documents_uri or mapping.get("DI_PUBLISHED_DOCUMENTS_URI")
        )
        direct_sections_uri = (
            published_sections_uri or mapping.get("DI_PUBLISHED_SECTIONS_URI")
        )
        direct_manifests_uri = (
            processing_manifests_uri or mapping.get("DI_PROCESSING_MANIFESTS_URI")
        )
        root_uri = surfaces_root_uri or mapping.get("DI_SURFACES_ROOT_URI")

        if any([direct_documents_uri, direct_sections_uri, direct_manifests_uri]):
            if not all([direct_documents_uri, direct_sections_uri, direct_manifests_uri]):
                raise ValueError(
                    "published surface URIs must be provided together"
                )
            surface_uris = SurfaceUris(
                published_documents_uri=direct_documents_uri or "",
                published_sections_uri=direct_sections_uri or "",
                processing_manifests_uri=direct_manifests_uri or "",
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
        )

    @classmethod
    def from_environment(cls, environment: Optional[Mapping[str, str]] = None):
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
        raise ValueError("{name} must be an integer".format(name=name)) from error
    if parsed < minimum:
        raise ValueError("{name} must be >= {minimum}".format(name=name, minimum=minimum))
    return parsed

