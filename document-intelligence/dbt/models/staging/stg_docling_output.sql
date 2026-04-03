with source as (
    select * from {{ source('bronze', 'raw_docling_output') }}
),
parsed as (
    select
        coalesce(document_version_id, file_id) as document_version_id,
        file_id,
        processed_at,
        policy_set_id,
        from_json(
            docling_json,
            'STRUCT<
                title: STRING,
                document_type: STRING,
                source_uri: STRING,
                sections: ARRAY<STRUCT<
                    heading: STRING,
                    level: INT,
                    content: STRING,
                    page_number: INT
                >>,
                tables: ARRAY<STRING>,
                metadata: MAP<STRING, STRING>,
                schema_version: STRING
            >'
        ) as doc
    from source
)
select
    document_version_id,
    file_id,
    processed_at,
    policy_set_id,
    doc.title,
    doc.document_type,
    doc.source_uri,
    doc.sections,
    doc.tables,
    doc.metadata,
    doc.schema_version
from parsed
