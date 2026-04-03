"""Runtime configuration helpers for local and Databricks execution."""

import os
from dataclasses import dataclass
from typing import Mapping, Optional

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
    ) -> "RuntimeSettings":
        effective_processing_version = (
            processing_version or mapping.get("DI_PROCESSING_VERSION") or "0.1.0-dev"
        )

        direct_documents_uri = published_documents_uri or mapping.get(
            "DI_PUBLISHED_DOCUMENTS_URI"
        )
        direct_sections_uri = published_sections_uri or mapping.get(
            "DI_PUBLISHED_SECTIONS_URI"
        )
        direct_manifests_uri = processing_manifests_uri or mapping.get(
            "DI_PROCESSING_MANIFESTS_URI"
        )
        root_uri = surfaces_root_uri or mapping.get("DI_SURFACES_ROOT_URI")

        if any([direct_documents_uri, direct_sections_uri, direct_manifests_uri]):
            if not all(
                [direct_documents_uri, direct_sections_uri, direct_manifests_uri]
            ):
                raise ValueError("published surface URIs must be provided together")
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
