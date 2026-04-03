with source as (
    select * from {{ source('bronze', 'landing_envelopes') }}
    where artifact_type = 'document_candidate'
),
renamed as (
    select
        ingestion_id,
        crawl_run_id,
        source_system,
        source_uri,
        cast(retrieved_at as timestamp) as retrieved_at,
        content_type,
        raw_object_uri,
        checksum,
        cast(http_status as int) as http_status,
        artifact_type,
        title,
        language,
        source_document_id,
        coalesce(country, 'UNKNOWN') as country,
        coalesce(jurisdiction, 'UNKNOWN') as jurisdiction,
        coalesce(document_class, 'unknown') as document_class,
        authority_name,
        authority_type,
        court_name,
        court_level,
        parent_uri,
        cast(discovery_depth as int) as discovery_depth,
        source_metadata,
        envelope_schema_version,
        adapter_version
    from source
    where http_status = 200
)
select * from renamed
