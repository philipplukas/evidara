{{
    config(
        materialized='table',
        comment='SCD2 document dimension with one row per (document_id, validity window).'
    )
}}

-- Grain: one row per (document_id, dbt_valid_from). The latest row per
-- document_id has dbt_valid_to IS NULL and is_current = true.

with identity as (
    select * from {{ ref('int_document_identity') }}
),

current_versions as (
    select
        document_id,
        document_version_id,
        ingestion_id,
        source_system,
        country,
        jurisdiction,
        document_class,
        language,
        retrieved_at,
        row_number() over (partition by document_id order by retrieved_at desc) = 1 as is_latest
    from identity
),

lifecycle as (
    select
        document_id,
        title,
        document_type,
        lifecycle_status,
        processed_at,
        dbt_valid_from,
        dbt_valid_to
    from {{ ref('snap_document_lifecycle') }}
)

select
    {{ generate_hash_id(["l.document_id", "l.dbt_valid_from"]) }} as document_sk,
    {{ generate_hash_id(["l.document_id"]) }} as document_nk_sk,
    l.document_id,
    c.document_version_id as current_version_id,
    c.source_system,
    c.country,
    c.jurisdiction,
    c.document_class,
    c.language,
    coalesce(l.title, '') as title,
    l.document_type,
    l.lifecycle_status,
    l.processed_at as latest_processed_at,
    c.retrieved_at as latest_retrieved_at,
    l.dbt_valid_from as valid_from,
    l.dbt_valid_to as valid_to,
    l.dbt_valid_to is null as is_current,
    current_timestamp() as refreshed_at
from lifecycle l
left join current_versions c
    on l.document_id = c.document_id and c.is_latest
