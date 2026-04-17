{#
    Custom schema resolver for Unity Catalog on Databricks.

    dbt's default behaviour prepends the target schema to the custom schema
    (producing e.g. ``dev_di_staging``). Under Unity Catalog we already have
    environment isolation at the catalog level (``evidara_document_intelligence_dev``
    vs ``evidara_document_intelligence_prod``), so we want the custom schema
    to be used verbatim.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
