select
  captured_resource_id,
  run_id,
  source_url,
  final_url,
  title,
  content_type,
  http_status,
  discovery_depth,
  checksum,
  fetched_at,
  created_at,
  updated_at
from captured_resources
where run_id = {{ run_id }}
order by created_at asc;
