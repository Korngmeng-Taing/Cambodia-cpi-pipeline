-- test_no_aeon_in_coicop_06
-- Asserts that AEON 1 and AEON 3 products (food, cosmetics, fashion, household)
-- never have products classified into COICOP 06 (Health / Pharmaceuticals).
select
    item_id,
    store_slug,
    canonical_name,
    coicop_division,
    coicop_method
from {{ ref('int_coicop_classified') }}
where store_slug in ('aeon', 'aeon3')
  and coicop_division = '06'
