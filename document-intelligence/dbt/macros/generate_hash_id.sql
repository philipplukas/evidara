{#
    Return SHA2-256 hash over the concatenation of the provided columns, using
    '||' as the separator. Non-string columns are cast to string before
    concatenation. Use for deriving stable surrogate keys from natural keys.

    Usage:
        select {{ generate_hash_id(['source_system', 'source_uri', 'checksum']) }} as document_version_id
#}
{% macro generate_hash_id(columns) %}
    sha2(concat_ws('||'
        {%- for column in columns -%}
            , cast({{ column }} as string)
        {%- endfor -%}
    ), 256)
{% endmacro %}
