{{
    config(
        materialized='incremental',
        unique_key='processing_manifest_id',
        incremental_strategy='merge',
        on_schema_change='merge',
        comment='Fact at processing-manifest grain: one row per processing attempt.'
    )
}}

-- Grain: one row per processing_manifest_id (one per processing attempt,
-- including failures and superseded results).
--
-- Inline dim attributes are carried on the fact for now. When dim tables land
-- (step 4), these get swapped for surrogate keys.

with manifests as (
    select * from {{ ref('stg_processing_manifests') }}
    {% if is_incremental() %}
    where coalesce(canonical_ready_at, current_timestamp())
          > (select coalesce(max(canonical_ready_at), cast('1970-01-01' as timestamp)) from {{ this }})
    {% endif %}
),

published as (
    select
        document_id,
        processing_manifest_id,
        document_revision,
        lifecycle_status,
        document_type,
        title,
        processed_at
    from {{ ref('stg_published_documents') }}
),

envelopes as (
    select
        ingestion_id,
        source_system,
        country,
        jurisdiction,
        document_class,
        authority_name,
        language
    from {{ ref('stg_landing_envelopes') }}
),

identity as (
    select
        document_id,
        document_version_id,
        ingestion_id
    from {{ ref('int_document_identity') }}
),

entities_by_version as (
    select
        document_version_id,
        count(*) as entities_count
    from {{ ref('int_entities') }}
    group by document_version_id
),

relations_by_version as (
    select
        document_version_id,
        count(*) as relations_count
    from {{ ref('int_relations') }}
    group by document_version_id
),

chunks_by_version as (
    select
        document_version_id,
        count(*) as chunk_count
    from {{ ref('embeddings_ready') }}
    group by document_version_id
),

events_by_version as (
    select
        document_version_id,
        count(*) as event_count,
        max(attempt_number) as max_attempt_number,
        min(event_timestamp) as first_event_at,
        max(event_timestamp) as last_event_at
    from {{ ref('stg_processing_events') }}
    group by document_version_id
),

supersession as (
    select distinct
        supersedes_processing_manifest_id as manifest_id,
        true as is_superseded
    from manifests
    where supersedes_processing_manifest_id is not null
),

dim_document as (
    select document_sk, document_id from {{ ref('dim_document') }} where is_current
),

dim_source_system as (
    select source_system_code from {{ ref('dim_source_system') }}
),

dim_jurisdiction as (
    select jurisdiction_code from {{ ref('dim_jurisdiction') }}
)

select
    m.processing_manifest_id,
    dd.document_sk,
    coalesce(dss.source_system_code, 'unknown') as source_system_code,
    coalesce(dj.jurisdiction_code, 'UNKNOWN') as jurisdiction_code,
    m.document_id,
    m.document_revision,
    id.document_version_id,
    m.supersedes_processing_manifest_id,

    -- status & flags
    m.status,
    p.lifecycle_status,
    m.status = 'canonical_ready' as is_success,
    coalesce(s.is_superseded, false) as is_superseded,
    m.failure_type is not null as has_failure,
    m.failure_type,
    m.failure_message,

    -- inline dim attributes (swapped for surrogate keys in step 4)
    m.processing_version,
    env.source_system,
    env.country,
    env.jurisdiction,
    env.document_class,
    env.authority_name,
    env.language,
    p.document_type,
    p.title,

    -- timestamps & latencies
    m.canonical_ready_at,
    p.processed_at,
    evs.first_event_at,
    evs.last_event_at,
    cast(unix_timestamp(evs.last_event_at) - unix_timestamp(evs.first_event_at) as double) as total_latency_s,

    -- counts from manifest
    m.document_count,
    m.section_count,
    m.citation_count,

    -- derived counts
    coalesce(ea.entities_count, 0) as entities_count,
    coalesce(ra.relations_count, 0) as relations_count,
    coalesce(ca.chunk_count, 0) as chunk_count,
    coalesce(evs.event_count, 0) as event_count,
    evs.max_attempt_number,

    current_timestamp() as fact_refreshed_at
from manifests m
left join published p
    on m.processing_manifest_id = p.processing_manifest_id
left join identity id
    on m.document_id = id.document_id
left join envelopes env
    on id.ingestion_id = env.ingestion_id
left join entities_by_version ea
    on id.document_version_id = ea.document_version_id
left join relations_by_version ra
    on id.document_version_id = ra.document_version_id
left join chunks_by_version ca
    on id.document_version_id = ca.document_version_id
left join events_by_version evs
    on id.document_version_id = evs.document_version_id
left join supersession s
    on m.processing_manifest_id = s.manifest_id
left join dim_document dd
    on m.document_id = dd.document_id
left join dim_source_system dss
    on env.source_system = dss.source_system_code
left join dim_jurisdiction dj
    on env.jurisdiction = dj.jurisdiction_code
