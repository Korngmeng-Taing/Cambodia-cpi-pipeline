-- test_no_retail_in_coicop_07
-- Asserts that grocery stores, supermarkets, pharmacies, and tech shops
-- never have products classified into COICOP 07 (Transport).
select
    item_id,
    store_slug,
    canonical_name,
    coicop_division,
    coicop_method
from {{ ref('int_coicop_classified') }}
where store_slug in ('communitypharma', 'delishop', 'arystore', 'samnangshop', 'khmer24', 'realestate', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk')
  and coicop_division = '07'

