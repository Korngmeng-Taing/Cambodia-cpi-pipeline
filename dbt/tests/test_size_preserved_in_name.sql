-- test_size_preserved_in_name
-- C2 regression: rows whose `size_norm` contains a recognized unit must also
-- have a matching unit token in `name_clean`. The previous _RE_PRICE regex
-- stripped bare "<digits><letters>" sequences ("330ml", "500g") thinking
-- they were prices; this test catches that reappearing.
select
    raw_price_id,
    scrape_date,
    store_slug,
    name_raw,
    name_clean,
    size_norm
from {{ ref('int_prices_cleaned') }}
where size_norm is not null
  and name_raw ~* '([0-9]+\s*(ml|g|kg|oz|lb|l|gram|grams|kilo|kilos|liter|liters|litre|litres|mls|gm))\b'
  and name_clean !~* '(ml|g|kg|oz|lb|l|gram|grams|kilo|kilos|liter|liters|litre|litres|mls|gm)\b'
limit 50
