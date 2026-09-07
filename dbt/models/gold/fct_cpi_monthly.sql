-- fct_cpi_monthly.sql
-- Monthly 12-Division & National CPI Aggregate Mart
-- NOTE: Authoritative single-writer is pipeline/cpi_calculator.py (CPICalculationEngine.save_monthly_cpi),
-- invoked by gold_cpi_dag.py (calculate_monthly_cpi_indices).
-- Disabled in dbt to guarantee single-writer consistency and prevent race conditions.
{{ config(
    enabled=false,
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
        sum(item_count) as item_count,
        sum(observation_count) as observation_count,
        count(distinct calculation_date) as active_days_in_month
    from daily_facts
    group by
        cpi_month,
        coicop_division
),
monthly_weighted as (
    select
        cpi_month,
        coicop_division,
        division_name,
        weight,
        monthly_division_index,
        round(
            (sum(case when monthly_division_index is not null then weight * monthly_division_index else 0 end) over (partition by cpi_month)
             / nullif(sum(case when monthly_division_index is not null then weight else 0 end) over (partition by cpi_month), 0))::numeric,
            4
        ) as monthly_headline_cpi,
        round(
            (sum(case when monthly_division_index is not null and coicop_division not in ('01', '04', '07') then weight * monthly_division_index else 0 end) over (partition by cpi_month)
             / nullif(sum(case when monthly_division_index is not null and coicop_division not in ('01', '04', '07') then weight else 0 end) over (partition by cpi_month), 0))::numeric,
            4
        ) as monthly_core_cpi,
        item_count,
        observation_count,
        active_days_in_month
    from monthly_aggregated
),

with_lags as (
    select
        curr.cpi_month,
        curr.coicop_division,
        curr.division_name,
        curr.weight,
        curr.monthly_division_index,
        curr.monthly_headline_cpi,
        curr.monthly_core_cpi,
        -- BUG FIX: Self-join on exact calendar intervals (1 month, 1 year)
        -- instead of LAG(n) which offsets by row count and breaks with monthly gaps.
        round(((curr.monthly_division_index - mom.monthly_division_index) / nullif(mom.monthly_division_index, 0) * 100.0)::numeric, 4) as mom_inflation_pct,
        round(((curr.monthly_division_index - yoy.monthly_division_index) / nullif(yoy.monthly_division_index, 0) * 100.0)::numeric, 4) as yoy_inflation_pct,
        round(((curr.monthly_headline_cpi - mom.monthly_headline_cpi) / nullif(mom.monthly_headline_cpi, 0) * 100.0)::numeric, 4) as headline_mom_inflation_pct,
        round(((curr.monthly_headline_cpi - yoy.monthly_headline_cpi) / nullif(yoy.monthly_headline_cpi, 0) * 100.0)::numeric, 4) as headline_yoy_inflation_pct,
        curr.item_count,
        curr.observation_count,
        curr.active_days_in_month,
        now() as created_at
    from monthly_weighted curr
    left join monthly_weighted mom
      on mom.coicop_division = curr.coicop_division
     and mom.cpi_month = (curr.cpi_month - interval '1 month')::date
    left join monthly_weighted yoy
      on yoy.coicop_division = curr.coicop_division
     and yoy.cpi_month = (curr.cpi_month - interval '1 year')::date
)
select * from with_lags
