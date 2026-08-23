-- cpi_div09_recreation
-- Gold analytical dataset for COICOP Division 09: Recreation and culture
{{ config(
    materialized='view',
    unique_key=['scrape_date', 'item_id']
) }}

select
    j.scrape_date,
    j.item_id,
    m.canonical_name,
    '09' as coicop_division,
    'Recreation and culture' as division_name,
    j.p_khr_jevons as current_price_khr,
    j.base_price_khr,
    j.jevons_index_base as item_index_base,
    j.unit_price_khr_jevons as unit_price_khr,
    j.n_quotes,
    j.n_stores,
    j.dod_price_change_pct,
    j.jevons_rel_dod,
    h.hedonic_adjusted_price_khr,
    h.adjustment_ratio as hedonic_adjustment_ratio
from {{ ref('fct_jevons_daily') }} j
left join {{ ref('dim_items') }} m
    on m.item_id = j.item_id
left join (
    select scrape_date, item_id, avg(hedonic_adjusted_price_khr) as hedonic_adjusted_price_khr, avg(adjustment_ratio) as adjustment_ratio
    from {{ source('silver', 'hedonic_adjusted_prices') }}
    group by scrape_date, item_id
) h on h.scrape_date = j.scrape_date and h.item_id = j.item_id
where j.coicop_division = '09'
