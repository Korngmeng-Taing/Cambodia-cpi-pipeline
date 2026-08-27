-- fct_daily_prices
-- Gold Layer Daily Price Fact Table (BI / Star Schema)
-- Grain: (scrape_date, store_slug, item_id)
-- Contains only essential metrics and dimension foreign keys.
-- 
-- IMPORTANT: This model is NOT the source for CPI calculation.
-- The CPI engine (pipeline/cpi_calculator.py) reads from silver.clean_store_prices
-- directly because it requires:
--   1. Cross-store geometric mean per item_id (not store-level grain)
--   2. Hedonic-adjusted prices from silver.hedonic_adjusted_prices
--   3. COICOP division/code from the classification pipeline
-- fct_daily_prices serves dim_items, dim_stores, and BI dashboards.
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['scrape_date', 'store_slug', 'item_id'],
    on_schema_change='append_new_columns',
    post_hook=[
        "create unique index if not exists uq_fct_daily_prices_grain on {{ this }} (scrape_date, store_slug, item_id)",
        "create index if not exists idx_fct_daily_prices_date on {{ this }} (scrape_date)",
        "create index if not exists idx_fct_daily_prices_item on {{ this }} (item_id)",
        "create index if not exists idx_fct_daily_prices_store on {{ this }} (store_slug)"
    ]
) }}

with grouped as (
    select
        p.scrape_date,
        p.store_slug,
        p.item_id,
        round(exp(avg(ln(p.price_khr)) filter (where p.price_khr > 0)), 2) as price_khr,
        min(p.original_price_khr) as original_price_khr,
        min(p.discount_pct) as discount_pct,
        bool_or(p.on_promo) as on_promo,
        min(p.size_value) as size_value,
        min(p.size_unit) as size_unit,
        max(p.pack_qty) as pack_qty,
        bool_and(p.cpi_eligible) as cpi_eligible,
        bool_or(p.is_outlier) as is_outlier,
        bool_or(p.is_fallback) as is_fallback
    from {{ ref('clean_store_prices') }} p
    where p.item_id is not null
      and p.price_khr > 0
    {% if is_incremental() %}
        {% if var('ds', '') and var('ds') != 'None' and var('ds') != 'null' and var('ds') != 'none' %}
            and p.scrape_date = '{{ var("ds") }}'::date
        {% else %}
            and p.scrape_date >= (select coalesce(max(scrape_date) - interval '2 days', '2020-01-01'::date) from {{ this }})
        {% endif %}
    {% endif %}
    group by
        p.scrape_date,
        p.store_slug,
        p.item_id
)
select
    scrape_date,
    store_slug,
    item_id,
    price_khr,
    original_price_khr,
    discount_pct,
    on_promo,
    case
        when lower(size_unit) in ('kg', 'kilo', 'kilos', 'kilogram', 'kilograms') and size_value > 0
            then round(price_khr / size_value, 2)
        when lower(size_unit) in ('g', 'gm', 'gram', 'grams') and size_value > 0
            then round(price_khr / (size_value / 1000.0), 2)
        when lower(size_unit) in ('l', 'ltr', 'litre', 'liter', 'litres', 'liters') and size_value > 0
            then round(price_khr / size_value, 2)
        when lower(size_unit) in ('ml', 'millilitre', 'milliliter', 'millilitres', 'milliliters') and size_value > 0
            then round(price_khr / (size_value / 1000.0), 2)
        else null
    end as unit_price_khr,
    size_value,
    size_unit,
    pack_qty,
    cpi_eligible,
    is_outlier,
    is_fallback
from grouped
