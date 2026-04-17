{#
    SCD2 snapshot of processing_manifest status transitions. Manifests are
    immutable after publication, but the 'status' field can move from
    canonical_ready to superseded when a newer revision lands. Snapshotting
    lets analytics track how long each manifest held each status.
#}

{% snapshot snap_processing_manifest %}

{{
    config(
        target_schema='di_snapshots',
        unique_key='processing_manifest_id',
        strategy='check',
        check_cols=['status', 'failure_type'],
        invalidate_hard_deletes=True
    )
}}

select
    processing_manifest_id,
    document_id,
    document_revision,
    status,
    failure_type,
    canonical_ready_at
from {{ ref('stg_processing_manifests') }}

{% endsnapshot %}
