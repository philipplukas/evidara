"""Explicit published surface definitions for document-intelligence."""

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class SurfaceColumn:
    name: str
    logical_type: str
    nullable: bool
    description: str


@dataclass(frozen=True)
class PublishedSurfaceDefinition:
    surface_name: str
    surface_version: int
    selector_kind: str
    selector_fields: tuple[str, ...]
    columns: tuple[SurfaceColumn, ...]
    description: str

    def column_names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)


PUBLISHED_DOCUMENTS = PublishedSurfaceDefinition(
    surface_name="published_documents",
    surface_version=1,
    selector_kind="record_key",
    selector_fields=("document_id", "processing_manifest_id"),
    description="Canonical document revisions published by document-intelligence.",
    columns=(
        SurfaceColumn("document_id", "string", False, "Stable logical document ID."),
        SurfaceColumn("document_revision", "integer", False, "Published document revision."),
        SurfaceColumn(
            "processing_manifest_id",
            "string",
            False,
            "Processing result that produced the document revision.",
        ),
        SurfaceColumn("provenance", "object", False, "Bundle and run lineage block."),
        SurfaceColumn(
            "primary_artifact_id",
            "string",
            False,
            "Selected primary artifact for this canonical revision.",
        ),
        SurfaceColumn("jurisdiction_id", "string", True, "Resolved jurisdiction reference."),
        SurfaceColumn("authority_id", "string", True, "Resolved authority reference."),
        SurfaceColumn("title", "string", False, "Canonical title."),
        SurfaceColumn("document_type", "string", True, "Canonical document type."),
        SurfaceColumn("effective_date", "date", True, "Resolved effective date."),
        SurfaceColumn("processed_at", "timestamp", False, "Canonical publication timestamp."),
        SurfaceColumn("processing_version", "string", False, "DI pipeline version."),
        SurfaceColumn("lifecycle_status", "string", False, "Lifecycle status."),
        SurfaceColumn("full_text", "string", False, "Normalized full text."),
        SurfaceColumn("body_text", "string", False, "Normalized body text."),
        SurfaceColumn("metadata", "object", True, "Low-risk canonical metadata."),
        SurfaceColumn("extensions", "object", True, "Non-canonical extension area."),
    ),
)


PUBLISHED_SECTIONS = PublishedSurfaceDefinition(
    surface_name="published_sections",
    surface_version=1,
    selector_kind="record_filter",
    selector_fields=("document_id", "processing_manifest_id"),
    description="Canonical section rows for one published document revision.",
    columns=(
        SurfaceColumn("section_id", "string", False, "Section identifier."),
        SurfaceColumn("document_id", "string", False, "Parent document ID."),
        SurfaceColumn("document_revision", "integer", False, "Parent document revision."),
        SurfaceColumn(
            "processing_manifest_id",
            "string",
            False,
            "Processing result that produced the section.",
        ),
        SurfaceColumn("provenance", "object", False, "Bundle and run lineage block."),
        SurfaceColumn("parent_section_id", "string", True, "Parent section ID when nested."),
        SurfaceColumn("ordinal", "integer", False, "Section order within the document."),
        SurfaceColumn("depth", "integer", False, "Section nesting depth."),
        SurfaceColumn("title", "string", True, "Section heading."),
        SurfaceColumn("content", "string", False, "Canonical section content."),
        SurfaceColumn("section_type", "string", True, "Section structural type."),
        SurfaceColumn("metadata", "object", True, "Additional section metadata."),
    ),
)


PROCESSING_MANIFESTS = PublishedSurfaceDefinition(
    surface_name="processing_manifests",
    surface_version=1,
    selector_kind="record_key",
    selector_fields=("processing_manifest_id",),
    description="Immutable processing result rows for canonical-ready or failed revisions.",
    columns=(
        SurfaceColumn(
            "processing_manifest_id",
            "string",
            False,
            "Immutable processing result ID.",
        ),
        SurfaceColumn("manifest_version", "integer", False, "Manifest contract version."),
        SurfaceColumn("document_id", "string", False, "Document identity."),
        SurfaceColumn("document_revision", "integer", False, "Published document revision."),
        SurfaceColumn("processing_version", "string", False, "DI pipeline version."),
        SurfaceColumn("status", "string", False, "Processing lifecycle state."),
        SurfaceColumn("provenance", "object", False, "Bundle and run lineage block."),
        SurfaceColumn(
            "input_bundle_manifest_ref",
            "object",
            False,
            "Reference to the consumed artifact bundle manifest.",
        ),
        SurfaceColumn(
            "selected_profiles",
            "object",
            False,
            "Profiles and resolution policies selected for processing.",
        ),
        SurfaceColumn(
            "reference_snapshot_set_ref",
            "string",
            True,
            "Reference snapshot set used during canonicalization.",
        ),
        SurfaceColumn(
            "published_document_ref",
            "object",
            True,
            "Published document surface reference for canonical-ready results.",
        ),
        SurfaceColumn(
            "published_sections_ref",
            "object",
            True,
            "Published sections surface reference for canonical-ready results.",
        ),
        SurfaceColumn(
            "canonical_ready_at",
            "timestamp",
            True,
            "Timestamp when this result became canonical-ready.",
        ),
        SurfaceColumn(
            "supersedes_processing_manifest_id",
            "string",
            True,
            "Older processing manifest superseded by this one.",
        ),
        SurfaceColumn("document_count", "integer", False, "Published document count."),
        SurfaceColumn("section_count", "integer", False, "Published section count."),
        SurfaceColumn("citation_count", "integer", False, "Published citation count."),
        SurfaceColumn("failure", "object", True, "Failure payload for failed processing."),
    ),
)


PUBLISHED_COMMENTARY_INSIGHTS = PublishedSurfaceDefinition(
    surface_name="published_commentary_insights",
    surface_version=1,
    selector_kind="record_filter",
    selector_fields=("document_id", "processing_manifest_id"),
    description="Non-canonical extractive commentary insights published by document-intelligence.",
    columns=(
        SurfaceColumn("insight_id", "string", False, "Stable commentary insight ID."),
        SurfaceColumn("document_id", "string", False, "Parent document ID."),
        SurfaceColumn("document_revision", "integer", False, "Parent document revision."),
        SurfaceColumn(
            "processing_manifest_id",
            "string",
            False,
            "Processing result that produced the insight.",
        ),
        SurfaceColumn("section_id", "string", True, "Section containing the support passage."),
        SurfaceColumn("citation_id", "string", True, "Citation row anchoring the insight when available."),
        SurfaceColumn("insight_type", "string", False, "Commentary insight taxonomy value."),
        SurfaceColumn("claim", "string", False, "Short extractive proposition or normalized label."),
        SurfaceColumn("display_text", "string", False, "Source passage snippet for UI rendering."),
        SurfaceColumn("support", "object", False, "Evidence references supporting the insight."),
        SurfaceColumn("referenced_authorities", "object", False, "Citations or provisions found in the passage."),
        SurfaceColumn("language", "string", True, "Primary source passage language."),
        SurfaceColumn("jurisdiction_id", "string", True, "Resolved jurisdiction reference."),
        SurfaceColumn("confidence", "float", False, "Deterministic confidence score."),
        SurfaceColumn("review_state", "string", False, "Review lifecycle state."),
        SurfaceColumn("generator", "object", False, "Extractor or model metadata."),
        SurfaceColumn("scores", "object", False, "Deterministic validator scores."),
        SurfaceColumn("metadata", "object", True, "Additional non-canonical metadata."),
    ),
)


SURFACE_DEFINITIONS: dict[str, PublishedSurfaceDefinition] = {
    definition.surface_name: definition
    for definition in (
        PUBLISHED_DOCUMENTS,
        PUBLISHED_SECTIONS,
        PROCESSING_MANIFESTS,
        PUBLISHED_COMMENTARY_INSIGHTS,
    )
}


def iter_surface_definitions() -> Iterable[PublishedSurfaceDefinition]:
    return SURFACE_DEFINITIONS.values()


def get_surface_definition(surface_name: str) -> PublishedSurfaceDefinition:
    return SURFACE_DEFINITIONS[surface_name]
