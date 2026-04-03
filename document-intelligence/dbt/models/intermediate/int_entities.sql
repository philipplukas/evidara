{{
    config(
        materialized='incremental',
        unique_key='entity_id',
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
exploded as (
    select
        coalesce(document_version_id, file_id) as document_version_id,
        file_id,
        section_idx,
        coalesce(model_name, nlp_policy_id) as model_name,
        processed_at,
        posexplode(
            from_json(
                entities_json,
                'ARRAY<STRUCT<
                    text: STRING,
                    label: STRING,
                    start_char: INT,
                    end_char: INT,
                    confidence: DOUBLE
                >>'
            )
        ) as (entity_pos, entity)
    from raw_nlp
    where entities_json is not null
)
select
    sha2(concat_ws('||', document_version_id, section_idx, cast(entity_pos as string), entity.label), 256) as entity_id,
    document_version_id,
    file_id,
    section_idx,
    entity.text as entity_text,
    entity.label as entity_label,
    entity.start_char,
    entity.end_char,
    entity.confidence,
    model_name,
    cast(processed_at as timestamp) as processed_at,
    current_timestamp() as transformed_at
from exploded
where entity.label in ({{ "'" + var('entity_labels') | join("', '") + "'" }})
