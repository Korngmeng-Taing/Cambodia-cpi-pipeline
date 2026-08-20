-- test_traps
-- Deterministic exception products must land on their expected COICOP division.
-- (Passes when no trap product is present in the daily fact; flags misclassifications.)
with trap_cases as (
    select 'COOKING WINE 750ML' as trap, '01' as expected
    union all select 'SOMERSBY CIDER 4X330ML', '02'
    union all select 'WOLF BLASS SHIRAZ 750ML', '02'
    union all select 'TVHC SLIPPER UNISEX', '03'
    union all select 'LIX FLOOR CLEANER 3.8L', '05'
    union all select 'TV COFFEE FILTER 40', '05'
    union all select 'GREEN ONION SLICER', '05'
    union all select 'LITTLE TREES BLACK ICE', '05'
    union all select 'LITTLE TREES WASH&WAX', '05'
    union all select 'MY-RING NOTES A5', '09'
    union all select 'WAKAME MIXED RICE WITH SALMON', '01'
    union all select 'SPICY BEEF HOT POT 270G', '01'
    union all select 'SUNPLAY SKIN AQUA SPF50', '12'
    union all select 'LIPICE', '12'
    union all select 'HOSPITAL CONSULTATION FEE', '06'
    union all select 'CLINIC VISIT', '06'
    union all select 'PRESCRIPTION GLASSES', '06'
    union all select 'CONTACT LENS', '06'
    union all select 'DRY CLEANING SERVICE', '03'
    union all select 'TAILOR ALTERATION', '03'
    union all select 'HAIRCUT', '12'
    union all select 'NAIL SALON', '12'
    union all select 'GYM MEMBERSHIP', '09'
    union all select 'CINEMA TICKET', '09'
    union all select 'MUSEUM ENTRY', '09'
    union all select 'TRAVEL INSURANCE', '12'
    union all select 'NAIL SCISSORS', '12'
    union all select 'NAIL SCISSOR', '12'
    union all select 'CUTICLE SCISSORS', '12'
    union all select 'MANICURE SET', '12'
    union all select 'TV SALTED MIXED NUTS', '01'
    union all select 'SALTED MIXED NUTS', '01'
    union all select 'FOEYCAI NAIL FILE BUFFER', '12'
    union all select 'NAIL FILE BUFFER', '12'
    union all select 'CHROY CHANGVAR CONDO FOR RENT', '04'
    union all select 'SERVICED APARTMENT FOR RENT', '04'
    union all select 'GREEK DRESSING', '01'
    union all select 'HOT WHEELS TRACK SET', '09'
)
select
    f.scrape_date,
    f.store_slug,
    f.item_id,
    f.name_clean,
    t.trap,
    t.expected,
    f.coicop_division as actual
from {{ ref('fct_daily_prices') }} f
join trap_cases t on position(upper(t.trap) in upper(f.name_clean)) > 0
where f.coicop_division <> t.expected
