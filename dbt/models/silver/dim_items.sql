-- dim_items
-- Unified canonical item dimension — one row per item_id with canonical metadata,
-- brand, barcode, size, unit of measure, store coverage, and COICOP division.
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key='item_id',
    on_schema_change='append_new_columns'
) }}

with match_stats as (
    select
        item_id,
        count(*) as match_count,
        mode() within group (order by match_method) as dominant_method,
        round(avg(confidence), 4) as avg_match_confidence
    from {{ source('silver', 'item_match_log') }}
    group by item_id
),
fact_stats as (
    select
        item_id::uuid as item_id,
        count(distinct store_slug) as store_count,
        mode() within group (order by size_unit) as unit_of_measure,
        min(scrape_date) as first_seen,
        max(scrape_date) as last_seen,
        bool_and(cpi_eligible) as is_active
    from {{ ref('fct_daily_prices') }}
    group by item_id
),
coicop_stats as (
    select distinct on (item_id::uuid)
        item_id::uuid as item_id,
        coicop_division,
        coicop_code
    from {{ ref('int_coicop_classified') }}
    order by
        item_id::uuid,
        case when coicop_division <> 'UNCLASSIFIED' then 1 else 2 end,
        coicop_confidence desc
)
select
    ci.item_id::text as item_id,
    ci.canonical_name,
    ci.brand,
    ci.barcode,
    ci.size_norm,
    ci.category as native_category,
    coalesce(cs.coicop_division, 'UNCLASSIFIED') as coicop_division,
    coalesce(cs.coicop_code, cs.coicop_division, 'UNCLASSIFIED') as coicop_code,
    fs.unit_of_measure,
    coalesce(fs.store_count, 0) as store_count,
    coalesce(ms.avg_match_confidence, 1.000) as avg_match_confidence,
    coalesce(fs.first_seen, ci.first_seen::date) as first_seen,
    coalesce(fs.last_seen, ci.last_seen::date) as last_seen,
    coalesce(fs.is_active, (ci.last_seen >= now() - interval '30 days')) as is_active,
    case
        when coalesce(fs.last_seen, ci.last_seen::date) >= current_date - interval '3 days'
             and coalesce(fs.first_seen, ci.first_seen::date) >= current_date - interval '7 days'
            then 'NEW_ENTRY'
        when coalesce(fs.last_seen, ci.last_seen::date) >= current_date - interval '3 days'
            then 'ACTIVE'
        when coalesce(fs.last_seen, ci.last_seen::date) >= current_date - interval '14 days'
            then 'TEMPORARILY_OUT_OF_STOCK'
        else 'DISCONTINUED'
    end as lifecycle_status,
    (current_date - coalesce(fs.last_seen, ci.last_seen::date)) as days_since_last_seen
from {{ source('silver', 'canonical_items') }} ci
left join match_stats ms on ms.item_id = ci.item_id
left join fact_stats fs on fs.item_id = ci.item_id
left join coicop_stats cs on cs.item_id = ci.item_id
