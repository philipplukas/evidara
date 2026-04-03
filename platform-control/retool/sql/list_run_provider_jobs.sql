select
  provider_job_id,
  run_id,
  provider,
  external_job_id,
  status,
  last_event_type,
  request_payload,
  response_payload,
  created_at,
  updated_at
from provider_jobs
where run_id = {{ run_id }}
order by created_at asc;
