-- fct_daily_prices
-- Final silver daily fact — one row per (scrape_date, store_slug, item_id)
-- with COICOP classification + KHR prices + quality flags.
-- The post-hook restores the grain constraint declared in sql/schema.sql: dbt builds
-- this table itself, so the primary key from the bootstrap DDL is gone after the
-- first (or any full-refresh) run, leaving writers that rely on
-- ON CONFLICT (scrape_date, store_slug, item_id) without a conflict target.
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['scrape_date', 'store_slug', 'item_id'],
    on_schema_change='append_new_columns',
    post_hook=[
        "create unique index if not exists uq_fct_daily_prices_grain on {{ this }} (scrape_date, store_slug, item_id)"
    ]
) }}

with classified as (
    -- Resolve a single COICOP row per (item_id, store_slug) defensively,
    -- in case int_coicop_classified ever has duplicates on the join key.
    select distinct on (item_id, store_slug)
        item_id,
        store_slug,
        coicop_division,
        coicop_method,
        coicop_confidence
    from {{ ref('int_coicop_classified') }}
    order by item_id, store_slug, coicop_confidence desc
),
grouped as (
    select
        p.scrape_date,
        p.store_slug,
        p.item_id::text as item_id,
        p.item_id::text as product_key,
        min(p.name_clean) as name_clean,
        min(p.category_native) as category_native,
        coalesce(min(c.coicop_division), 'UNCLASSIFIED') as coicop_division,
        coalesce(min(c.coicop_method), 'unclassified') as coicop_method,
        coalesce(min(c.coicop_confidence), 0.000) as coicop_confidence,
        min(p.currency) as currency,
        min(p.price_original_curr) as price_original_curr,
        min(p.original_price_curr) as original_price_curr,
        min(p.original_price_khr) as original_price_khr,
        min(p.discount_pct) as discount_pct,
        bool_or(p.on_promo) as on_promo,
        round(exp(avg(ln(p.price_khr)) filter (where p.price_khr > 0)), 2) as price_khr,
        min(p.size_value) as size_value,
        min(p.size_unit) as size_unit,
        max(p.pack_qty) as pack_qty,
        bool_or(p.is_outlier) as is_outlier,
        bool_and(p.cpi_eligible) as cpi_eligible,
        bool_or(p.is_fallback) as is_fallback,
        max(p.scraped_at) as scraped_at
    from {{ ref('int_prices_cleaned') }} p
    left join classified c
        on c.item_id = p.item_id::text
       and c.store_slug = p.store_slug
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
    product_key,
    name_clean,
    category_native,
    coicop_division,
    coicop_method,
    coicop_confidence,
    currency,
    price_original_curr,
    original_price_curr,
    original_price_khr,
    discount_pct,
    on_promo,
    price_khr,
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
    is_outlier,
    cpi_eligible,
    is_fallback,
    scraped_at
from grouped
