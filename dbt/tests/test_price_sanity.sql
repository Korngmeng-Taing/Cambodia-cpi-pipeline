-- test_price_sanity
-- No CPI-eligible observation may have a non-positive or absurd price.
select
    scrape_date,
    store_slug,
    item_id,
    name_clean,
    price_khr
from {{ ref('fct_daily_prices') }}
where cpi_eligible = true
  and (price_khr <= 0 or price_khr > 100000000)
