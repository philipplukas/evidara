select
  s.source_id,
  s.name,
  s.description,
  s.source_type,
  s.document_family,
  s.status,
  s.created_at,
  s.updated_at,
  j.name as jurisdiction_name,
  a.name as authority_name
from sources s
join jurisdictions j on j.jurisdiction_id = s.jurisdiction_id
join authorities a on a.authority_id = s.authority_id
order by s.created_at desc;
