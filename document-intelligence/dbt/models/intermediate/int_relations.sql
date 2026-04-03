{{
    config(
        materialized='incremental',
        unique_key='relation_id',
        incremental_strategy='merge',
        on_schema_change='merge'
    )
}}

with raw_nlp as (
    select * from {{ source('bronze', 'raw_nlp_annotations') }}
    {% if is_incremental() %}
    where processed_at > (select max(processed_at) from {{ this }})
    {% endif %}
),
exploded_relations as (
    select
        coalesce(document_version_id, file_id) as document_version_id,
        section_idx,
        coalesce(nlp_policy_id, model_name) as nlp_policy_id,
        processed_at,
        posexplode(
            from_json(
                relations_json,
                'ARRAY<STRUCT<
                    head_text: STRING,
                    head_idx: INT,
                    dep_text: STRING,
                    dep_idx: INT,
                    relation: STRING
                >>'
            )
        ) as (rel_pos, rel)
    from raw_nlp
    where relations_json is not null
)
select
    sha2(concat_ws('||', document_version_id, section_idx, cast(rel_pos as string)), 256) as relation_id,
    document_version_id,
    section_idx,
    rel.head_text,
    rel.head_idx,
    rel.dep_text,
    rel.dep_idx,
    rel.relation as relation_type,
    nlp_policy_id,
    cast(processed_at as timestamp) as processed_at,
    current_timestamp() as transformed_at
from exploded_relations
where rel.relation in (
    'nsubj', 'nsubjpass', 'dobj', 'pobj', 'appos',
    'compound', 'prep', 'agent', 'attr', 'nmod'
)
