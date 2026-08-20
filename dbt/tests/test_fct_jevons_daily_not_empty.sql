-- test_fct_jevons_daily_not_empty
-- The Silver elementary Jevons fact must produce at least one row per division
-- after the latest successful Bronze ingestion. Empty results mean either the
-- price fact has no rows OR base_prices is missing for the configured base period.
select
    j.coicop_division,
    count(*) as row_count,
    max(j.scrape_date) as latest_scrape_date
from {{ ref('fct_jevons_daily') }} j
group by j.coicop_division
having count(*) = 0
