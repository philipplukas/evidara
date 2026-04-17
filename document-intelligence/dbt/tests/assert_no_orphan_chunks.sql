-- Every chunk in embeddings_ready must map to a section that still exists in
-- int_document_sections. Orphans indicate the chunking step ran against a
-- section that has since been deleted (or the reverse: sections were rebuilt
-- but chunks were not).

select
    c.chunk_id,
    c.section_id,
    c.document_version_id
from {{ ref('embeddings_ready') }} c
left join {{ ref('int_document_sections') }} s using (section_id)
where s.section_id is null
