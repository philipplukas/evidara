{#
    Approximate character length for a given token count, assuming an average
    of 4 characters per token. Centralises the heuristic used by the chunking
    logic in marts/embeddings_ready; swap this body when a true tokenizer UDF
    is available.

    Usage:
        substr(content, 1, {{ approx_token_chars(var('chunk_size_tokens')) }})
#}
{% macro approx_token_chars(tokens) %}
    ({{ tokens }} * 4)
{% endmacro %}
