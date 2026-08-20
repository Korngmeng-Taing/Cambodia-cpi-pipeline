-- test_no_retail_stores_in_coicop_04
-- Asserts that grocery stores, supermarkets, pharmacies, and tech shops
-- never have products classified into COICOP 04 (Housing & Utilities).
select
    item_id,
    store_slug,
    canonical_name,
    coicop_division,
    coicop_method
from {{ ref('int_coicop_classified') }}
where store_slug in ('communitypharma', 'pharmacy', 'u-care', 'ucare', 'delishop', 'aeon', 'aeon3', 'samnangshop', 'arystore', 'bookmebus', 'redbus')
  and coicop_division = '04'
