-- test_dim_items_unique
-- The Silver canonical item dimension must be unique by item_id and have
-- a non-empty canonical_name for every row. Null names usually mean a bad
-- merge between item_match_log and fct_daily_prices.
select
    item_id,
    canonical_name,
    coicop_division
from {{ ref('dim_items') }}
where canonical_name is null
   or trim(canonical_name) = ''
   or item_id is null
   or item_id = ''
