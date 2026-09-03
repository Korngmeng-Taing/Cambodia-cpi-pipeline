-- fct_cpi_monthly.sql
-- Monthly 12-Division & National CPI Aggregate Mart
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['cpi_month', 'coicop_division'],
    on_schema_change='append_new_columns',
    post_hook=[
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_fct_cpi_monthly ON {{ this }} (cpi_month, coicop_division)"
    ]
) }}

with daily_facts as (
    select
        calculation_date,
        date_trunc('month', calculation_date)::date as cpi_month,
        coicop_division,
        division_name,
        weight,
        division_index,
        headline_cpi,
        core_cpi,
        item_count,
        observation_count
    from {{ source('gold', 'fct_cpi_daily') }}
    {% if is_incremental() %}
        where calculation_date >= (select coalesce(max(cpi_month) - interval '14 months', '2020-01-01'::date) from {{ this }})
    {% endif %}
),
monthly_aggregated as (
    select
        cpi_month,
        coicop_division,
        max(division_name) as division_name,
        max(weight) as weight,
        round(avg(division_index)::numeric, 4) as monthly_division_index,
        round(avg(headline_cpi)::numeric, 4) as monthly_headline_cpi,
        round(avg(core_cpi)::numeric, 4) as monthly_core_cpi,
        sum(item_count) as item_count,
        sum(observation_count) as observation_count,
        count(distinct calculation_date) as active_days_in_month
    from daily_facts
    group by
        cpi_month,
        coicop_division
),
with_lags as (
    select
        cpi_month,
        coicop_division,
        division_name,
        weight,
        monthly_division_index,
        monthly_headline_cpi,
        monthly_core_cpi,
        round(((monthly_division_index - lag(monthly_division_index) over (partition by coicop_division order by cpi_month)) / nullif(lag(monthly_division_index) over (partition by coicop_division order by cpi_month), 0) * 100.0)::numeric, 4) as mom_inflation_pct,
        round(((monthly_division_index - lag(monthly_division_index, 12) over (partition by coicop_division order by cpi_month)) / nullif(lag(monthly_division_index, 12) over (partition by coicop_division order by cpi_month), 0) * 100.0)::numeric, 4) as yoy_inflation_pct,
        round(((monthly_headline_cpi - lag(monthly_headline_cpi) over (partition by coicop_division order by cpi_month)) / nullif(lag(monthly_headline_cpi) over (partition by coicop_division order by cpi_month), 0) * 100.0)::numeric, 4) as headline_mom_inflation_pct,
        round(((monthly_headline_cpi - lag(monthly_headline_cpi, 12) over (partition by coicop_division order by cpi_month)) / nullif(lag(monthly_headline_cpi, 12) over (partition by coicop_division order by cpi_month), 0) * 100.0)::numeric, 4) as headline_yoy_inflation_pct,
        item_count,
        observation_count,
        active_days_in_month,
        now() as created_at
    from monthly_aggregated
)
select * from with_lags
