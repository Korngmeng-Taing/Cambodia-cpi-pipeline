-- test_coicop_08_stores_only
-- Asserts that:
-- 1. 100% of products from phone shops and telecoms map to COICOP 08.
-- 2. ZERO products from any other store can map to COICOP 08.
select
    item_id,
    store_slug,
    canonical_name,
    coicop_division,
    coicop_method
from {{ ref('int_coicop_classified') }}
where
    -- Case 1: Tech/telecom store NOT mapped to 08
    (store_slug in ('arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') and coicop_division <> '08')
    or
    -- Case 2: Non-tech store erroneously mapped to 08
    (store_slug not in ('arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') and coicop_division = '08')
