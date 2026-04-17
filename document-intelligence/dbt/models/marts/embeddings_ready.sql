{{
    config(
        materialized='table',
        comment='Text chunks ready for vector embedding.',
        post_hook=["{{ zorder_by(['document_version_id', 'section_id']) }}"]
    )
}}

with sections as (
    select * from {{ ref('int_document_sections') }}
),
metadata as (
    select
        file_id,
        from_json(metadata_json, 'MAP<STRING,STRING>') as meta
    from {{ source('bronze', 'raw_metadata') }}
),
joined as (
    select
        s.*,
        m.meta
    from sections s
    left join metadata m using (file_id)
),
chunked as (
    select
        {{ generate_hash_id(["document_version_id", "section_idx", "chunk_idx"]) }} as chunk_id,
        document_version_id,
        file_id,
        section_id,
        section_idx,
        chunk_idx,
        document_title,
        document_type,
        source_uri,
        section_heading,
        page_number,
        substr(
            section_content,
            greatest(
                1,
                chunk_idx * {{ approx_token_chars(var('chunk_size_tokens')) }}
                - chunk_idx * {{ approx_token_chars(var('chunk_overlap_tokens')) }}
            ),
            {{ approx_token_chars(var('chunk_size_tokens')) }}
        ) as chunk_text,
        meta,
        transformed_at
    from joined
    lateral view posexplode(
        sequence(
            0,
            greatest(
                0,
                cast(ceil(content_length_chars / ({{ approx_token_chars(var('chunk_size_tokens')) }} * 1.0)) as int) - 1
            )
        )
    ) t as chunk_idx
)
select
    chunk_id,
    document_version_id,
    file_id,
    section_id,
    section_idx,
    chunk_idx,
    document_title,
    document_type,
    source_uri,
    section_heading,
    page_number,
    chunk_text,
    length(chunk_text) as chunk_length_chars,
    meta,
    current_timestamp() as refreshed_at
from chunked
where chunk_text is not null
  and length(trim(chunk_text)) > 50
