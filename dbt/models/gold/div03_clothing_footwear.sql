-- cpi_div03_clothing_footwear
-- Gold analytical dataset for COICOP Division 03: Clothing and footwear
{{ config(
    materialized='view',
    unique_key=['scrape_date', 'item_id']
) }}

select
    j.scrape_date,
    j.item_id,
    m.canonical_name,
    '03' as coicop_division,
    'Clothing and footwear' as division_name,
    j.p_khr_jevons as current_price_khr,
    j.base_price_khr,
    j.jevons_index_base as item_index_base,
    j.unit_price_khr_jevons as unit_price_khr,
    j.n_quotes,
    j.n_stores,
    j.dod_price_change_pct,
    j.jevons_rel_dod
from {{ ref('fct_jevons_daily') }} j
left join {{ ref('dim_items') }} m
    on m.item_id = j.item_id
where j.coicop_division = '03'
