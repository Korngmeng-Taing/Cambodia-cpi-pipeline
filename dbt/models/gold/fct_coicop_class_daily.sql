-- fct_coicop_class_daily
-- Authoritative Elementary Aggregate Mart at 4-Digit COICOP Class Level (e.g. 01.1.1 Bread and Cereals)
-- Compiles Jevons Elementary Aggregate Index from product price relatives.
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['calculation_date', 'coicop_code'],
    on_schema_change='append_new_columns'
) }}

with elementary as (
    select
        calculation_date,
        coicop_division,
        coicop_code,
        price_ratio,
        observation_count,
        is_imputed
    from {{ source('gold', 'fct_elementary_indices') }}
    where price_ratio > 0
    {% if is_incremental() %}
        and calculation_date >= (select coalesce(max(calculation_date) - interval '2 days', '2020-01-01'::date) from {{ this }})
    {% endif %}
)
select
    calculation_date,
    coicop_division,
    coicop_code,
    round((exp(avg(ln(price_ratio))) * 100.0)::numeric, 4) as class_index,
    count(*) as item_count,
    sum(observation_count) as total_observations,
    sum(case when is_imputed then 1 else 0 end) as imputed_item_count,
    now() as created_at
from elementary
group by
    calculation_date,
    coicop_division,
    coicop_code
