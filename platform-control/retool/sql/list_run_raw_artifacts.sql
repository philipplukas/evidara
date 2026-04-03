select
  artifact_id,
  run_id,
  source_id,
  source_version_id,
  storage_path,
  content_type,
  artifact_metadata,
  created_at,
  updated_at
from raw_artifacts
where run_id = {{ run_id }}
order by created_at asc;
