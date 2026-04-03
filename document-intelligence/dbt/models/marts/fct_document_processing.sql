select
  document_id,
  max(processed_at) as latest_processed_at,
  count(*) as published_revision_count
from {{ ref('stg_published_documents') }}
group by 1
