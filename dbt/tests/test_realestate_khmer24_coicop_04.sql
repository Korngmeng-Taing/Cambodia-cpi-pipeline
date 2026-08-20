-- test_realestate_khmer24_coicop_04
-- Ensures 100% of products from khmer24 and realestate map EXCLUSIVELY to COICOP 04 (Housing).
select
    item_id,
    store_slug,
    canonical_name,
    coicop_division,
    coicop_method
from {{ ref('int_coicop_classified') }}
where store_slug in ('khmer24', 'realestate')
  and coicop_division <> '04'
