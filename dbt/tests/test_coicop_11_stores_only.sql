-- test_coicop_11_stores_only
-- Asserts that:
-- 1. 100% of listings/meals from hotels and restaurants map to COICOP 11.
-- 2. ZERO products from any other store can map to COICOP 11.
select
    item_id,
    store_slug,
    canonical_name,
    coicop_division,
    coicop_method
from {{ ref('int_coicop_classified') }}
where
    -- Case 1: Hotel/restaurant store NOT mapped to 11
    (store_slug in ('sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') and coicop_division <> '11')
    or
    -- Case 2: Non-hotel/restaurant store erroneously mapped to 11
    (store_slug not in ('sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') and coicop_division = '11')
