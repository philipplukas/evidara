with source as (
    select * from {{ source('published', 'processing_manifests') }}
)
select
    processing_manifest_id,
    manifest_version,
    document_id,
    document_revision,
    processing_version,
    status,
    provenance,
    input_bundle_manifest_ref,
    selected_profiles,
    reference_snapshot_set_ref,
    published_document_ref,
    published_sections_ref,
    cast(canonical_ready_at as timestamp) as canonical_ready_at,
    supersedes_processing_manifest_id,
    cast(document_count as int) as document_count,
    cast(section_count as int) as section_count,
    cast(citation_count as int) as citation_count,
    failure,
    failure.failure_type as failure_type,
    failure.message as failure_message
from source
