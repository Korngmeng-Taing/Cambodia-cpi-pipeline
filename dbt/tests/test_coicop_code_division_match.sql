-- test_coicop_code_division_match
-- Ensures that the 2-digit prefix of coicop_code ALWAYS matches coicop_division.

select
    item_id,
    store_slug,
    coicop_division,
    coicop_code,
    coicop_method
from {{ ref('int_coicop_classified') }}
where coicop_division not in ('UNCLASSIFIED', 'REVIEW')
  and coicop_code not in ('UNCLASSIFIED', 'REVIEW')
  and lpad(split_part(coicop_code, '.', 1), 2, '0') <> lpad(coicop_division, 2, '0')

union all

select
    item_id,
    store_slug,
    coicop_division,
    coicop_code,
    coicop_method
from {{ ref('clean_store_prices') }}
where coicop_division not in ('UNCLASSIFIED', 'REVIEW')
  and coicop_code not in ('UNCLASSIFIED', 'REVIEW')
  and lpad(split_part(coicop_code, '.', 1), 2, '0') <> lpad(coicop_division, 2, '0')
