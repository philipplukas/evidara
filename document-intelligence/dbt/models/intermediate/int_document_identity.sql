{{
    config(
        materialized='incremental',
        unique_key='document_version_id',
        incremental_strategy='merge',
        on_schema_change='merge'
    )
}}

with envelopes as (
    select * from {{ ref('stg_landing_envelopes') }}
    {% if is_incremental() %}
    where retrieved_at > (select max(retrieved_at) from {{ this }})
    {% endif %}
),
identity_derived as (
    select
        ingestion_id,
        source_system,
        source_uri,
        source_document_id,
        checksum,
        country,
        jurisdiction,
        document_class,
        language,
        case
            when source_document_id is not null
                then {{ generate_hash_id(["source_system", "source_document_id", "coalesce(language, '')"]) }}
            else {{ generate_hash_id(["source_system", "source_uri"]) }}
        end as document_id,
        {{ generate_hash_id(["source_system", "source_uri", "checksum"]) }} as document_version_id,
        retrieved_at
    from envelopes
),
versioned as (
    select
        i.*,
        {% if is_incremental() %}
        not exists (
            select 1 from {{ this }} prev
            where prev.document_id = i.document_id
              and prev.content_hash = i.checksum
        ) as is_new_version
        {% else %}
        true as is_new_version
        {% endif %}
    from identity_derived i
)
select
    document_id,
    document_version_id,
    ingestion_id,
    source_system,
    source_uri,
    source_document_id,
    checksum as content_hash,
    country,
    jurisdiction,
    document_class,
    language,
    is_new_version,
    retrieved_at,
    current_timestamp() as identity_resolved_at
from versioned
