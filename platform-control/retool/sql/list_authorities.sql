select
  authority_id,
  jurisdiction_id,
  name,
  slug,
  created_at,
  updated_at
from authorities
order by name asc;
