-- fct_laspeyres_headline_daily
-- Daily headline Laspeyres CPI in the Silver layer: weighted aggregation of the
-- 12 COICOP division indices produced by fct_laspeyres_daily.
{{ config(
    materialized='view'
) }}

with daily_headline as (
    select
        scrape_date,
        '{{ var("base_period") }}' as base_period,
        round(
            sum(category_index_value * (weight_pct / 100.0))
            / nullif(sum(weight_pct / 100.0), 0),
            4
        ) as headline_cpi,
        count(distinct coicop_division) as divisions_present,
        sum(weight_pct) as total_weight_present,
        'Laspeyres' as formula
    from {{ ref('fct_laspeyres_daily') }}
    group by scrape_date
)

select
    curr.scrape_date,
    curr.base_period,
    curr.headline_cpi,
    curr.divisions_present,
    curr.total_weight_present,
    curr.formula,
    round(
        (curr.headline_cpi - prev.headline_cpi) / nullif(prev.headline_cpi, 0) * 100.0,
        3
    ) as dod_inflation_pct
from daily_headline curr
left join daily_headline prev
    on prev.scrape_date = (curr.scrape_date - interval '1 day')::date
