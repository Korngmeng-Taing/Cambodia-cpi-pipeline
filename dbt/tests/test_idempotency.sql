-- test_idempotency
-- The daily fact grain (scrape_date, store_slug, item_id) must be unique.
select
    scrape_date,
    store_slug,
    item_id,
    count(*) as row_count
from {{ ref('fct_daily_prices') }}
group by scrape_date, store_slug, item_id
having count(*) > 1
