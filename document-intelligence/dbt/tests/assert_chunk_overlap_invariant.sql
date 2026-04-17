-- Within a section, chunk_idx values must be dense and monotonically
-- increasing starting from 0. Gaps or duplicates indicate the posexplode of
-- the sequence() window misbehaved.

with chunks as (
    select
        section_id,
        chunk_idx,
        row_number() over (partition by section_id order by chunk_idx) - 1 as expected_idx
    from {{ ref('embeddings_ready') }}
)
select
    section_id,
    chunk_idx,
    expected_idx
from chunks
where chunk_idx <> expected_idx
