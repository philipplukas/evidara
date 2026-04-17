{{
    config(
        materialized='table',
        comment='Document dimension (Type 1; will be upgraded to SCD2 via snapshot in step 5).'
    )
}}

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
        row_number() over (partition by document_id order by retrieved_at desc) = 1 as is_current
    from identity
),

published as (
    select
        document_id,
        title,
        document_type,
        lifecycle_status,
        processed_at
    from {{ ref('stg_published_documents') }}
),

latest_published as (
    select
        document_id,
        max_by(title, processed_at) as title,
        max_by(document_type, processed_at) as document_type,
        max_by(lifecycle_status, processed_at) as lifecycle_status,
        max(processed_at) as latest_processed_at
    from published
    group by document_id
)

select
    {{ generate_hash_id(["c.document_id"]) }} as document_sk,
    c.document_id,
    c.document_version_id as current_version_id,
    c.source_system,
    c.country,
    c.jurisdiction,
    c.document_class,
    c.language,
    coalesce(p.title, '') as title,
    p.document_type,
    p.lifecycle_status,
    p.latest_processed_at,
    c.retrieved_at as latest_retrieved_at,
    current_timestamp() as refreshed_at
from current_versions c
left join latest_published p using (document_id)
where c.is_current
