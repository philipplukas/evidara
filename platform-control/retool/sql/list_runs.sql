select
  r.run_id,
  r.source_id,
  r.source_version_id,
  r.mode,
  r.status,
  r.started_at,
  r.completed_at,
  r.artifacts_count,
  r.captured_resources_count,
  r.failure_reason,
  r.created_at,
  r.updated_at,
  s.name as source_name,
  sv.version_label
from runs r
join sources s on s.source_id = r.source_id
join source_versions sv on sv.source_version_id = r.source_version_id
order by r.created_at desc;
