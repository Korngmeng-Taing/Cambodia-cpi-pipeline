-- fct_laspeyres_daily
-- Higher-level Laspeyres aggregation across 12 COICOP divisions in the Silver layer.
-- Uses fixed base-period expenditure weights (Cambodia NIS standard) to aggregate
-- elementary Jevons price relatives into daily category and headline CPI indices.
{{ config(
    materialized='view',
    unique_key=['scrape_date', 'coicop_division']
) }}

with category_indices as (
    select
        j.scrape_date,
        j.coicop_division,
        w.division_name,
        w.weight_pct,
        round(exp(avg(ln(nullif(j.p_khr_jevons / nullif(j.base_price_khr, 0), 0)))) * 100.0, 4) as category_index_value,
        count(*) as n_items,
        count(distinct j.item_id) as unique_products
    from {{ ref('fct_jevons_daily') }} j
    inner join {{ source('gold', 'coicop_weights') }} w
        on w.coicop_division = j.coicop_division
    where j.p_khr_jevons > 0
      and j.base_price_khr > 0
    group by
        j.scrape_date,
        j.coicop_division,
        w.division_name,
        w.weight_pct
),

category_with_prev as (
    select
        curr.scrape_date,
        curr.coicop_division,
        curr.division_name,
        curr.weight_pct,
        curr.category_index_value,
        curr.n_items,
        curr.unique_products,
        round((curr.category_index_value - prev.category_index_value) / nullif(prev.category_index_value, 0) * 100.0, 3) as dod_category_change_pct
    from category_indices curr
    left join category_indices prev
        on curr.coicop_division = prev.coicop_division
       and prev.scrape_date = (curr.scrape_date - interval '1 day')::date
)

select
    scrape_date,
    coicop_division,
    division_name,
    weight_pct,
    category_index_value,
    n_items,
    unique_products,
    dod_category_change_pct,
    'Laspeyres' as formula_type
from category_with_prev
