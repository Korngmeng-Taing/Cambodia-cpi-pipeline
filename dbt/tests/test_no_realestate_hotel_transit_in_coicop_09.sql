-- test_no_realestate_hotel_transit_in_coicop_09
-- Asserts that real estate portals, hotels, transit portals, and dedicated phone shops
-- never have products/listings classified into COICOP 09 (Recreation and Culture).
select
    item_id,
    store_slug,
    canonical_name,
    coicop_division,
    coicop_method
from {{ ref('int_coicop_classified') }}
where store_slug in ('khmer24', 'realestate', 'bookmebus', 'redbus', 'redmebus', 'samnangshop', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk')
  and coicop_division = '09'
