{{
    config(
        materialized='incremental',
        unique_key='section_id',
        incremental_strategy='merge',
        on_schema_change='merge'
    )
}}

with staged as (
    select * from {{ ref('stg_docling_output') }}
    {% if is_incremental() %}
    where processed_at > (select max(processed_at) from {{ this }})
    {% endif %}
),
exploded as (
    select
        document_version_id,
        file_id,
        title as document_title,
        document_type,
        source_uri,
        processed_at,
        posexplode(sections) as (section_idx, section)
    from staged
    where sections is not null
)
select
    {{ generate_hash_id(["document_version_id", "section_idx"]) }} as section_id,
    document_version_id,
    file_id,
    section_idx,
    document_title,
    document_type,
    source_uri,
    section.heading as section_heading,
    section.level as heading_level,
    section.content as section_content,
    section.page_number,
    length(section.content) as content_length_chars,
    cast(processed_at as timestamp) as processed_at,
    current_timestamp() as transformed_at
from exploded
where section.content is not null
  and length(trim(section.content)) > 0
