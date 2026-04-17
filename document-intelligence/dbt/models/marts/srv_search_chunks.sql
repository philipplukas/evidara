{{
    config(
        materialized='table',
        comment='Chunk-level serving model for search and vector ingestion.',
        post_hook=["{{ zorder_by(['document_id', 'document_version_id']) }}"]
    )
}}

with chunks as (
    select * from {{ ref('embeddings_ready') }}
),
doc_serving as (
    select
        document_version_id,
        document_id,
        source_system,
        title,
        language,
        country,
        jurisdiction,
        document_class,
        authority_name,
        is_current_version
    from {{ ref('srv_search_documents') }}
    where is_current_version = true
),
sections as (
    select
        document_version_id,
        section_idx,
        section_heading,
        heading_level
    from {{ ref('int_document_sections') }}
)
select
    c.chunk_id,
    c.file_id as ingestion_id,
    d.document_id,
    c.section_id,
    d.document_version_id,
    d.source_system,
    d.title as document_title,
    d.language,
    d.country,
    d.jurisdiction,
    d.document_class,
    d.authority_name,
    s.section_heading,
    s.heading_level,
    c.page_number,
    c.chunk_text,
    c.chunk_length_chars,
    c.chunk_idx,
    d.is_current_version,
    current_timestamp() as indexed_at
from chunks c
join doc_serving d using (document_version_id)
left join sections s on s.document_version_id = d.document_version_id
  and s.section_idx = c.section_idx
where d.is_current_version = true
