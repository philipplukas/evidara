{#
    Post-hook helper: OPTIMIZE ... ZORDER BY ... on the current model.
    Usage in model config:
        post_hook=["{{ zorder_by(['document_id', 'document_version_id']) }}"]
#}
{% macro zorder_by(columns) %}
    {% if target.type == 'databricks' and not flags.FULL_REFRESH %}
        optimize {{ this }}
        zorder by ({{ columns | join(', ') }})
    {% else %}
        select 1 as _noop
    {% endif %}
{% endmacro %}
