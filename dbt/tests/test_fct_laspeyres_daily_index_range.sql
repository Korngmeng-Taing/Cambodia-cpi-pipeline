-- test_fct_laspeyres_daily_index_range
-- Higher-level Laspeyres category index must be a sane positive number.
-- A value <= 0 indicates a broken base period or division weights; a value
-- outside [50, 500] indicates an extreme inflation spike that warrants review.
select
    scrape_date,
    coicop_division,
    category_index_value,
    weight_pct,
    n_items
from {{ ref('fct_laspeyres_daily') }}
where category_index_value is null
   or category_index_value <= 0
   or category_index_value > 500
   or weight_pct <= 0
   or weight_pct > 100
