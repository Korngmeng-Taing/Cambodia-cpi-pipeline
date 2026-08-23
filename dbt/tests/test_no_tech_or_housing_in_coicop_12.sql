-- test_no_tech_or_housing_in_coicop_12
-- Asserts that tech shops, real estate portals, hotels, transit portals, and fuel stations
-- never have products classified into COICOP 12 (Miscellaneous Goods & Personal Care).
select
    item_id,
    store_slug,
    canonical_name,
    coicop_division,
    coicop_method
from {{ ref('int_coicop_classified') }}
where store_slug in ('arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi', 'khmer24', 'realestate', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk', 'bookmebus', 'redbus', 'new_gasoline')
  and coicop_division = '12'
