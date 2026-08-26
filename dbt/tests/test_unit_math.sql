-- test_unit_math
-- When a parseable size exists, unit_price_khr must equal price_khr / size
-- (converted to the base kg/l unit), within rounding tolerance.
select
    scrape_date,
    store_slug,
    item_id,
    price_khr,
    size_value,
    size_unit,
    unit_price_khr,
    abs(unit_price_khr - expected_unit_price) as unit_deviation
from (
    select
        scrape_date,
        store_slug,
        item_id,
        price_khr,
        size_value,
        size_unit,
        unit_price_khr,
        case
            when lower(size_unit) = 'kg' and size_value > 0 then price_khr / size_value
            when lower(size_unit) = 'g'  and size_value > 0 then price_khr / (size_value / 1000.0)
            when lower(size_unit) = 'l'  and size_value > 0 then price_khr / size_value
            when lower(size_unit) = 'ml' and size_value > 0 then price_khr / (size_value / 1000.0)
            else null
        end as expected_unit_price
    from {{ ref('fct_daily_prices') }}
    where cpi_eligible = true
) t
where expected_unit_price is not null
  and unit_price_khr is not null
  and abs(unit_price_khr - expected_unit_price) > 0.5
