-- test_coicop_code_format
-- Ensures all classified records have a valid 3-tier dotted coicop_code (e.g. '01.1.1')
-- and never fall back to bare 2-digit division codes (e.g. '01').

select
    item_id,
    store_slug,
    coicop_division,
    coicop_code,
    coicop_method
from {{ ref('int_coicop_classified') }}
where coicop_code not in ('UNCLASSIFIED', 'REVIEW')
  and coicop_code !~ '^[0-9]{2}\.[0-9]{1,2}\.[0-9]{1,2}$'
  and coicop_code not like '%.unclassified'
