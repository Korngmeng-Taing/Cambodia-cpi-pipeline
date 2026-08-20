-- fct_jevons_daily
-- Elementary Jevons aggregation at the canonical item level in the Silver layer.
-- Computes unweighted geometric mean prices across stores, Jevons index relative to base period,
-- and day-on-day Jevons price relatives.
{{ config(
    materialized='view',
    unique_key=['scrape_date', 'item_id']
) }}

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
),

daily_jevons as (
    select
        scrape_date,
        item_id,
        coicop_division,
        -- Unit-price-aware elementary price (mirrors gold_procedures.sql & views.sql):
    -- use per-kg/L unit prices only when every quote carries a comparable base dimension,
    -- else fall back to shelf price so pack-size changes cannot masquerade as inflation.
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
        item_id,
        coicop_division
)

select
    curr.scrape_date,
    curr.item_id,
    curr.coicop_division,
    curr.p_khr_jevons,
    b.base_price_khr,
    round((curr.p_khr_jevons / nullif(b.base_price_khr, 0)) * 100.0, 4) as jevons_index_base,
    curr.unit_price_khr_jevons,
    curr.n_quotes,
    curr.n_stores,
    round((curr.p_khr_jevons - prev.p_khr_jevons) / nullif(prev.p_khr_jevons, 0) * 100.0, 3) as dod_price_change_pct,
    round(curr.p_khr_jevons / nullif(prev.p_khr_jevons, 0), 4) as jevons_rel_dod
from daily_jevons curr
left join {{ source('gold', 'base_prices') }} b
    on b.product_key = curr.item_id
   and b.base_period = '{{ var("base_period") }}'
left join daily_jevons prev
    on curr.item_id = prev.item_id
   and prev.scrape_date = (curr.scrape_date - interval '1 day')::date
