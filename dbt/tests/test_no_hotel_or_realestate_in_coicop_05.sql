-- test_no_hotel_or_realestate_in_coicop_05
-- Asserts that real estate portals, hotels, and bus booking sites
-- never have products/listings classified into COICOP 05 (Furnishings & Household Equipment).
select
    item_id,
    store_slug,
    canonical_name,
    coicop_division,
    coicop_method
from {{ ref('int_coicop_classified') }}
where store_slug in ('khmer24', 'realestate', 'bookmebus', 'redbus', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk')
  and coicop_division = '05'
