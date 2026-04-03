{{
    config(
        materialized='table',
        comment='BI analytics mart for document-intelligence operations.'
    )
}}

with ingestion_by_source as (
    select
        source_system,
        country,
        jurisdiction,
        document_class,
        date_trunc('day', retrieved_at) as ingestion_day,
        count(*) as documents_ingested,
        count(distinct crawl_run_id) as crawl_runs
    from {{ ref('stg_landing_envelopes') }}
    group by 1, 2, 3, 4, 5
),
processing_outcomes as (
    select
        cv.status,
        date_trunc('day', cv.last_updated_at) as outcome_day,
        count(*) as document_count,
        avg(cv.attempt_count) as avg_attempts,
        sum(case when cv.status = 'dead_letter' then 1 else 0 end) as dead_letter_count
    from {{ ref('int_control_versions') }} cv
    group by 1, 2
),
entity_distribution as (
    select
        entity_label,
        count(*) as entity_occurrences,
        count(distinct document_version_id) as documents_with_label,
        avg(confidence) as avg_confidence
    from {{ ref('int_entities') }}
    group by 1
),
stage_latency as (
    select
        stage,
        avg(
            unix_timestamp(
                lead(event_timestamp) over (
                    partition by document_version_id
                    order by event_timestamp
                )
            ) - unix_timestamp(event_timestamp)
        ) / 60.0 as avg_stage_duration_minutes
    from {{ ref('stg_processing_events') }}
    where event_type in ('started', 'completed')
    group by 1
)
select
    'ingestion_by_source' as metric_table,
    to_json(struct(*)) as data
from ingestion_by_source

union all

select
    'processing_outcomes',
    to_json(struct(*))
from processing_outcomes

union all

select
    'entity_distribution',
    to_json(struct(*))
from entity_distribution

union all

select
    'stage_latency',
    to_json(struct(*))
from stage_latency
