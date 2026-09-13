-- fct_cpi_nis_comparison.sql
-- Gold Layer: Tracking Error & Ground-Truth Benchmark Comparison Mart
-- Evaluates pipeline pipeline-calculated monthly CPI vs. official NIS releases.
{{ config(
    materialized='view',
    post_hook=[
        "COMMENT ON VIEW {{ this }} IS 'Evaluates high-frequency scraped CPI nowcasting against official NIS Cambodia benchmarks with tracking error, MAE, and directional accuracy.'"
    ]
) }}

with pipeline_monthly as (
    select distinct on (cpi_month)
        cpi_month,
        monthly_headline_cpi as pipeline_headline_cpi,
        monthly_core_cpi as pipeline_core_cpi,
        headline_mom_inflation_pct as pipeline_mom_pct,
        headline_yoy_inflation_pct as pipeline_yoy_pct,
        active_days_in_month,
        item_count as total_basket_items,
        observation_count as total_observations
    from {{ source('gold', 'fct_cpi_monthly') }}
    order by cpi_month, created_at desc
),
nis_benchmark as (
    select
        cpi_month,
        headline_cpi as nis_headline_cpi,
        core_cpi as nis_core_cpi,
        mom_inflation_pct as nis_mom_pct,
        yoy_inflation_pct as nis_yoy_pct,
        cpi_division_01 as nis_div_01_food,
        cpi_division_02 as nis_div_02_alcohol,
        cpi_division_03 as nis_div_03_clothing,
        cpi_division_04 as nis_div_04_housing,
        cpi_division_05 as nis_div_05_furnishings,
        cpi_division_06 as nis_div_06_health,
        cpi_division_07 as nis_div_07_transport,
        cpi_division_08 as nis_div_08_communication,
        cpi_division_09 as nis_div_09_recreation,
        cpi_division_10 as nis_div_10_education,
        cpi_division_11 as nis_div_11_restaurants,
        cpi_division_12 as nis_div_12_miscellaneous,
        release_date as nis_release_date,
        source_notes as nis_source_notes
    from {{ source('gold', 'dim_nis_official_cpi') }}
),
nis_anchor as (
    select nis_headline_cpi as anchor_nis_headline
    from nis_benchmark
    where cpi_month = '2026-08-01'
    limit 1
),
joined as (
    select
        coalesce(p.cpi_month, n.cpi_month) as cpi_month,
        p.pipeline_headline_cpi,
        n.nis_headline_cpi,
        
        -- Spliced / Rebased Pipeline CPI to NIS Base (Oct-Dec 2006 = 100)
        round((p.pipeline_headline_cpi / 100.0 * coalesce(a.anchor_nis_headline, 219.007))::numeric, 4) as pipeline_headline_cpi_rebased_to_nis,
        round(((p.pipeline_headline_cpi / 100.0 * coalesce(a.anchor_nis_headline, 219.007)) - n.nis_headline_cpi)::numeric, 4) as headline_rebased_error,
        round(abs((p.pipeline_headline_cpi / 100.0 * coalesce(a.anchor_nis_headline, 219.007)) - n.nis_headline_cpi)::numeric, 4) as headline_rebased_abs_error,
        
        -- Raw Base Level Difference (Pipeline 2026=100 vs NIS 2006=100)
        round((p.pipeline_headline_cpi - n.nis_headline_cpi)::numeric, 4) as headline_raw_base_gap,
        
        p.pipeline_core_cpi,
        n.nis_core_cpi,
        
        -- Inflation Rate Comparisons
        p.pipeline_mom_pct,
        n.nis_mom_pct,
        round((p.pipeline_mom_pct - n.nis_mom_pct)::numeric, 4) as mom_diff_pct_points,
        case
            when p.pipeline_mom_pct is not null and n.nis_mom_pct is not null then
                case
                    when (p.pipeline_mom_pct > 0 and n.nis_mom_pct > 0)
                      or (p.pipeline_mom_pct < 0 and n.nis_mom_pct < 0)
                      or (p.pipeline_mom_pct = 0 and n.nis_mom_pct = 0)
                    then true
                    else false
                end
            else null
        end as directional_concordance,
        
        p.pipeline_yoy_pct,
        n.nis_yoy_pct,
        round((p.pipeline_yoy_pct - n.nis_yoy_pct)::numeric, 4) as yoy_diff_pct_points,
        
        -- 12 Division Official Benchmarks
        n.nis_div_01_food,
        n.nis_div_02_alcohol,
        n.nis_div_03_clothing,
        n.nis_div_04_housing,
        n.nis_div_05_furnishings,
        n.nis_div_06_health,
        n.nis_div_07_transport,
        n.nis_div_08_communication,
        n.nis_div_09_recreation,
        n.nis_div_10_education,
        n.nis_div_11_restaurants,
        n.nis_div_12_miscellaneous,

        -- Provenance & Metadata
        p.active_days_in_month,
        p.total_basket_items,
        p.total_observations,
        n.nis_release_date,
        n.nis_source_notes
    from pipeline_monthly p
    full outer join nis_benchmark n on n.cpi_month = p.cpi_month
    left join nis_anchor a on true
)
select * from joined
order by cpi_month desc
