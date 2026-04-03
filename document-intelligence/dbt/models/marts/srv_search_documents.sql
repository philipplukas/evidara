{{
    config(
        materialized='table',
        comment='Document-level serving model for search.'
    )
}}

with identity as (
    select * from {{ ref('int_document_identity') }}
),
docling as (
    select
        document_version_id,
        policy_set_id,
        title,
        document_type
    from {{ ref('stg_docling_output') }}
),
sections_agg as (
    select
        document_version_id,
        count(*) as section_count,
        sum(content_length_chars) as total_chars,
        max(page_number) as page_count,
        concat_ws(' ', collect_list(section_content)) as search_text,
        collect_list(section_heading) as headings
    from {{ ref('int_document_sections') }}
    group by document_version_id
),
entities_agg as (
    select
        document_version_id,
        collect_set(entity_text) filter (where entity_label = 'ORG') as orgs,
        collect_set(entity_text) filter (where entity_label in ('DATE', 'LAW')) as legal_refs,
        count(*) as entity_count
    from {{ ref('int_entities') }}
    group by document_version_id
),
control as (
    select
        document_version_id,
        status,
        current_stage
    from {{ ref('int_control_versions') }}
    where status = 'done'
),
envelopes as (
    select * from {{ ref('stg_landing_envelopes') }}
),
current_versions as (
    select
        document_id,
        document_version_id,
        row_number() over (
            partition by document_id
            order by retrieved_at desc
        ) = 1 as is_current_version
    from identity
)
select
    i.document_id,
    i.document_version_id,
    env.source_system,
    env.source_uri,
    env.source_document_id,
    coalesce(d.title, env.title) as title,
    env.language,
    env.country,
    env.jurisdiction,
    env.document_class,
    env.authority_name,
    env.authority_type,
    env.court_name,
    env.court_level,
    d.policy_set_id,
    sa.section_count,
    sa.total_chars,
    sa.page_count,
    sa.headings,
    sa.search_text,
    ea.orgs,
    ea.legal_refs,
    ea.entity_count,
    env.retrieved_at as publication_date,
    cv.is_current_version,
    current_timestamp() as indexed_at
from identity i
join control ctl using (document_version_id)
join envelopes env using (ingestion_id)
left join docling d using (document_version_id)
left join sections_agg sa using (document_version_id)
left join entities_agg ea using (document_version_id)
join current_versions cv using (document_version_id, document_id)
