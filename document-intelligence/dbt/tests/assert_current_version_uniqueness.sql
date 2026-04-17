-- Each document_id must have exactly one row with is_current_version = true
-- in srv_search_documents. A duplicate indicates the row_number() partition in
-- the model is broken; zero indicates no current version exists.

with per_document as (
    select
        document_id,
        count_if(is_current_version) as current_versions
    from {{ ref('srv_search_documents') }}
    group by document_id
)
select *
from per_document
where current_versions <> 1
