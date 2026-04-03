select
  sv.source_version_id,
  sv.source_id,
  sv.extractor_profile_id,
  sv.version_label,
  sv.status,
  sv.acquisition_spec,
  sv.created_at,
  sv.updated_at,
  s.name as source_name
from source_versions sv
join sources s on s.source_id = sv.source_id
where sv.source_id = {{ source_id }}
order by sv.created_at desc;
