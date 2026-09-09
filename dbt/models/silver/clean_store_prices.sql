-- clean_store_prices
-- Silver Layer: Unified clean daily store price observations table.
-- Appends & cleans daily scraped price observations across all stores with standardized units,
-- currency conversion (KHR), promo clamping, outlier flags, and COICOP ladder classification.
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key='raw_price_id',
    on_schema_change='append_new_columns',
    post_hook=[
        "CREATE INDEX IF NOT EXISTS idx_clean_store_prices_scrape_date_store ON {{ this }} (scrape_date, store_slug)",
        "CREATE INDEX IF NOT EXISTS idx_clean_store_prices_store_item ON {{ this }} (store_slug, item_id)",
        "CREATE INDEX IF NOT EXISTS idx_clean_store_prices_coicop_code ON {{ this }} (coicop_code)",
        "CREATE INDEX IF NOT EXISTS idx_clean_store_prices_coicop_division ON {{ this }} (coicop_division)"
    ]
) }}

{% if flags.FULL_REFRESH and ('clean_store_prices' in selected_resources or 'silver.clean_store_prices' in selected_resources) %}
    {{ exceptions.raise_compiler_error("Full refresh on partitioned table silver.clean_store_prices is prohibited to protect partition tree. Use incremental refresh with --vars '{\"reclassify_all\": true}' instead.") }}
{% endif %}

with cleaned_prices as (
    select
        p.*,
        lower(p.name_clean) as name_clean_lower,
        lower(regexp_replace(trim(p.name_clean), '\s+', ' ', 'g')) as norm_name,
        lower(trim(coalesce(p.category_native, ''))) as norm_category
    from {{ ref('int_prices_cleaned') }} p
    where p.price_khr > 0
    {% if is_incremental() %}
        {% if var('ds', '') and var('ds') != 'None' and var('ds') != 'null' and var('ds') != 'none' %}
            and p.scrape_date = '{{ var("ds") }}'::date
        {% else %}
            and p.scrape_date >= (select coalesce(max(scrape_date) - interval '7 days', '2020-01-01'::date) from {{ this }})
        {% endif %}
    {% endif %}
),
classified as (
    select distinct on (item_id, store_slug)
        item_id,
        store_slug,
        coicop_division,
        coicop_code,
        coicop_method,
        coicop_confidence
    from {{ ref('int_coicop_classified') }}
    order by item_id, store_slug, coicop_confidence desc
),
enriched_observations as (
    select
        p.raw_price_id,
        p.scrape_date,
        p.store_slug,
        p.source_name,
        p.item_id::text as item_id,
        p.name_raw,
        p.name_clean,
        p.category_native,
        p.brand,
        p.barcode,
        p.currency,
        p.price_original_curr,
        p.original_price_curr,
        p.usd_khr_rate,
        p.price_khr,
        p.original_price_khr,
        p.discount_pct,
        p.on_promo,
        p.size_norm,
        p.size_value,
        p.size_unit,
        p.pack_qty,
        p.unit_price_khr,
        coalesce(c.coicop_division, 'UNCLASSIFIED') as coicop_division,
        coalesce(c.coicop_code, 'UNCLASSIFIED') as coicop_code,
        coalesce(c.coicop_method, 'unclassified') as coicop_method,
        coalesce(c.coicop_confidence, 0.000) as coicop_confidence,
        p.is_outlier,
        p.cpi_eligible,
        p.is_fallback,
        p.fallback_reason,
        p.match_method,
        p.match_confidence,
        p.scraped_at
    from cleaned_prices p
    left join classified c
        on c.item_id = p.item_id::text
       and c.store_slug = p.store_slug
    where p.price_khr is not null and p.price_khr > 0
)

select
    raw_price_id,
    scrape_date,
    store_slug,
    source_name,
    item_id,
    name_raw,
    name_clean,
    category_native,
    brand,
    barcode,
    currency,
    price_original_curr,
    original_price_curr,
    usd_khr_rate,
    price_khr,
    original_price_khr,
    discount_pct,
    on_promo,
    size_norm,
    size_value,
    size_unit,
    pack_qty,
    unit_price_khr,
    coicop_division,
    -- BUG FIX: Guarantee coicop_code prefix strictly matches coicop_division.
    -- If an override or fallback changed division, derive the proper subcode.
    case
        when coicop_code is not null and coicop_code ~ '^\d{2}\.\d{1,2}\.\d{1,2}$'
             and lpad(split_part(coicop_code, '.', 1), 2, '0') = coicop_division
        then coicop_code
        when coicop_code is not null and coicop_code ~ '^\d{2}\.unclassified$'
             and lpad(split_part(coicop_code, '.', 1), 2, '0') = coicop_division
        then coicop_code
        else {{ coicop_code_from_division("coicop_division") }}
    end as coicop_code,
    coicop_method,
    coicop_confidence,
    is_outlier,
    cpi_eligible,
    is_fallback,
    fallback_reason,
    match_method,
    match_confidence,
    scraped_at
from enriched_observations
