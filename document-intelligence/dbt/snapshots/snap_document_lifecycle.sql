{#
    SCD2 snapshot of the lifecycle_status for each published document. The
    check strategy is used because published_documents does not carry a true
    "updated_at" column - we snapshot whenever (title, document_type,
    lifecycle_status) change.
#}

{% snapshot snap_document_lifecycle %}

{{
    config(
        target_schema='di_snapshots',
        unique_key='document_id',
        strategy='check',
        check_cols=['title', 'document_type', 'lifecycle_status'],
        invalidate_hard_deletes=True
    )
}}

select
    document_id,
    title,
    document_type,
    lifecycle_status,
    processed_at
from {{ ref('stg_published_documents') }}

{% endsnapshot %}
