{{ config(
    materialized='view',
    schema='silver'
) }}

-- fct_jevons_daily
-- Pure Elementary Jevons geometric mean aggregation at the canonical item level in the Silver layer.
-- Calculates only the store-unweighted geometric mean price (p_khr_jevons) without price relatives or base indices.

with clean_obs as (
    select
        scrape_date,
        item_id,
        coicop_division,
        price_khr,
        unit_price_khr,
        size_unit,
        store_slug
    from {{ ref('fct_daily_prices') }}
    where cpi_eligible = true
      and is_outlier = false
      and is_fallback = false
      and price_khr > 0
)

select
    scrape_date,
    item_id,
    max(coicop_division) as coicop_division,
    -- Unit-price-aware elementary geometric mean price
    round(
        case
            when count(*) filter (where unit_price_khr > 0) = count(*)
             and count(distinct case when size_unit in ('kg','g') then 1 when size_unit in ('l','ml') then 2 end) = 1
            then exp(avg(ln(unit_price_khr)) filter (where unit_price_khr > 0))
            else exp(avg(ln(price_khr)) filter (where price_khr > 0))
        end,
        2
    ) as p_khr_jevons,
    round(exp(avg(ln(nullif(unit_price_khr, 0)))), 2) as unit_price_khr_jevons,
    count(*) as n_quotes,
    count(distinct store_slug) as n_stores
from clean_obs
group by
    scrape_date,
    item_id
