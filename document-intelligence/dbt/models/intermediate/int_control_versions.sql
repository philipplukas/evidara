{{
    config(
        materialized='incremental',
        unique_key='document_version_id',
        incremental_strategy='merge',
        on_schema_change='merge'
    )
}}

with events as (
    select * from {{ ref('stg_processing_events') }}
    {% if is_incremental() %}
    where event_timestamp > (select max(last_updated_at) from {{ this }})
    {% endif %}
),
latest_event as (
    select
        document_version_id,
        ingestion_id,
        stage as current_stage,
        event_type as current_event_type,
        event_timestamp as last_event_at,
        error_type,
        error_message,
        row_number() over (
            partition by document_version_id
            order by event_timestamp desc, attempt_number desc
        ) as rn
    from events
),
attempt_counts as (
    select
        document_version_id,
        count(*) filter (where event_type = 'failed') as failed_attempt_count,
        count(*) filter (where event_type = 'completed') as completed_stage_count,
        max(attempt_number) as max_attempt_number
    from events
    group by document_version_id
),
control as (
    select
        le.document_version_id,
        le.ingestion_id,
        le.current_stage,
        case
            when le.current_event_type = 'completed'
             and le.current_stage = 'serving' then 'done'
            when le.current_event_type = 'failed'
             and ac.failed_attempt_count >= 3 then 'dead_letter'
            when le.current_event_type = 'failed' then 'retryable'
            when le.current_event_type = 'started' then 'in_progress'
            else 'processing'
        end as status,
        ac.failed_attempt_count,
        ac.completed_stage_count,
        ac.max_attempt_number as attempt_count,
        le.error_type as last_error_type,
        le.error_message as last_error_message,
        le.last_event_at as last_updated_at
    from latest_event le
    join attempt_counts ac using (document_version_id)
    where le.rn = 1
)
select * from control
