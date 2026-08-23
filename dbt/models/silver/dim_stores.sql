-- dim_stores
-- Conformed store & source master dimension — one row per store_slug with source metadata,
-- channel classification, default COICOP division, and lifecycle scrape stats.
{{ config(
    materialized='table'
) }}

with store_metadata as (
    select
        store_slug,
        store_name,
        source_type,
        channel,
        default_currency,
        default_coicop_division,
        is_active
    from {{ ref('coicop_store_defaults') }}
),
activity_stats as (
    select
        store_slug,
        count(*) as total_observations,
        count(distinct item_id) as distinct_products_count,
        min(scrape_date) as first_scraped_at,
        max(scrape_date) as last_scraped_at
    from {{ ref('fct_daily_prices') }}
    group by store_slug
)
select
    sm.store_slug,
    sm.store_name,
    sm.source_type,
    sm.channel,
    sm.default_currency,
    sm.default_coicop_division,
    sm.is_active,
    coalesce(ast.total_observations, 0) as total_observations,
    coalesce(ast.distinct_products_count, 0) as distinct_products_count,
    ast.first_scraped_at,
    ast.last_scraped_at
from store_metadata sm
left join activity_stats ast on ast.store_slug = sm.store_slug
