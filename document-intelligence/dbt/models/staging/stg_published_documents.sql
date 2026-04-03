select
  document_id,
  document_revision,
  processing_manifest_id,
  title,
  document_type,
  processed_at,
  processing_version,
  lifecycle_status
from {{ source('published', 'published_documents') }}
