{{
    config(
        materialized='table',
        comment='Unified document knowledge base. One row per document version with metadata and entity roll-up.'
    )
}}

with docs as (
    select * from {{ ref('stg_docling_output') }}
),
metadata as (
    select
        r.file_id,
        r.source_url,
        r.mime_type,
        r.ingested_at,
        from_json(m.metadata_json, 'MAP<STRING,STRING>') as scraped_meta
    from {{ source('bronze', 'raw_documents') }} r
    left join {{ source('bronze', 'raw_metadata') }} m using (file_id)
),
sections_agg as (
    select
        document_version_id,
        file_id,
        count(*) as section_count,
        sum(content_length_chars) as total_content_chars,
        max(page_number) as page_count,
        collect_list(section_heading) as headings
    from {{ ref('int_document_sections') }}
    group by document_version_id, file_id
),
entities_agg as (
    select
        document_version_id,
        file_id,
        count(*) as entity_count,
        count(distinct entity_label) as unique_label_count,
        collect_set(entity_text) as unique_entities
    from {{ ref('int_entities') }}
    group by document_version_id, file_id
)
select
    d.document_version_id,
    d.file_id,
    d.title as document_title,
    d.document_type,
    m.source_url,
    m.mime_type,
    m.ingested_at,
    m.scraped_meta,
    d.metadata as docling_metadata,
    d.schema_version as docling_schema_version,
    sa.section_count,
    sa.total_content_chars,
    sa.page_count,
    sa.headings,
    ea.entity_count,
    ea.unique_label_count,
    ea.unique_entities,
    cast(d.processed_at as timestamp) as docling_processed_at,
    current_timestamp() as refreshed_at
from docs d
left join metadata m using (file_id)
left join sections_agg sa using (document_version_id, file_id)
left join entities_agg ea using (document_version_id, file_id)
