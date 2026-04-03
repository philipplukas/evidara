with source as (
    select * from {{ source('bronze', 'document_processing_events') }}
)
select
    event_id,
    document_version_id,
    ingestion_id,
    stage,
    event_type,
    cast(attempt_number as int) as attempt_number,
    cast(event_timestamp as timestamp) as event_timestamp,
    error_type,
    error_message,
    artifact_uri,
    cast(event_metadata as string) as event_metadata
from source
