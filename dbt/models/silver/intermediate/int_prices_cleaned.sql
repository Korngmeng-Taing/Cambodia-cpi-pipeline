-- int_prices_cleaned
-- One row per raw observation, cleaned & typed:
--   - USD -> KHR conversion via the MEF daily rate (fallback 4044)
--   - original_price_khr computed once at Silver (prevents downstream FX double-counting)
--   - promo discount clamped to [0%, 95%]
--   - unit price (KHR per base unit) derived from package size when parseable
--   - quality flags (outlier / cpi_eligible / fallback)
--   - name_clean: Khmer-aware normalization + uppercase + stripped of promo/price noise
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key='raw_price_id',
    on_schema_change='append_new_columns',
    post_hook=[
        "CREATE INDEX IF NOT EXISTS idx_int_prices_cleaned_date_item ON {{ this }} (scrape_date, item_id)",
        "CREATE INDEX IF NOT EXISTS idx_int_prices_cleaned_raw_price_id ON {{ this }} (raw_price_id)",
        "CREATE INDEX IF NOT EXISTS idx_int_prices_cleaned_store ON {{ this }} (store_slug)"
    ]
) }}

with exchange as (
    select execution_date, rate
    from {{ source('staging', 'exchange_rates') }}
),
raw as (
    select
        rp.raw_price_id,
        iml.item_id,
        iml.match_method,
        iml.confidence as match_confidence,
        rp.store_id as store_slug,
        rp.source_name,
        rp.item_description_raw as name_raw,
        rp.raw_payload ->> 'category_native' as category_native,
        rp.raw_payload ->> 'brand' as brand,
        rp.raw_payload ->> 'barcode' as barcode,
        rp.raw_payload ->> 'package_size' as size_norm,
        rp.raw_payload ->> 'is_fallback' as is_fallback_raw,
        rp.raw_payload ->> 'fallback_reason' as fallback_reason,
        (rp.raw_payload ->> 'original_price')::numeric as original_price_curr,
        rp.price as price_original_curr,
        rp.currency,
        rp.scraped_at,
        rp.scraped_at::date as scrape_date
    from {{ source('bronze', 'raw_prices') }} rp
    left join {{ source('silver', 'item_match_log') }} iml
        on iml.raw_price_id = rp.raw_price_id
    where rp.price > 0
    {% if is_incremental() %}
        {% if var('ds', '') != '' %}
            and rp.scraped_at::date = '{{ var("ds") }}'::date
        {% else %}
            and rp.scraped_at::date >= (select coalesce(max(scrape_date) - interval '7 days', '2020-01-01'::date) from {{ this }})
        {% endif %}
    {% endif %}
),
parsed as (
    select
        raw.*,
        coalesce(er.rate, 4044.0) as usd_khr_rate,
        case when upper(raw.currency) = 'KHR' then raw.price_original_curr
             else raw.price_original_curr * coalesce(er.rate, 4044.0)
        end as price_khr,
        case
            when raw.original_price_curr is null then null
            when upper(raw.currency) = 'KHR' then raw.original_price_curr
            else raw.original_price_curr * coalesce(er.rate, 4044.0)
        end as original_price_khr,
        coalesce(
            (regexp_match(coalesce(raw.size_norm, ''), '([0-9]+)\s*[xX*]\s*([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]+)'))[1]::numeric,
            1
        ) as pack_qty,
        coalesce(
            (regexp_match(coalesce(raw.size_norm, ''), '([0-9]+)\s*[xX*]\s*([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]+)'))[2]::numeric,
            (regexp_match(coalesce(raw.size_norm, ''), '([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]+)'))[1]::numeric,
            null
        ) as size_value,
        lower(coalesce(
            (regexp_match(coalesce(raw.size_norm, ''), '([0-9]+)\s*[xX*]\s*([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]+)'))[3],
            (regexp_match(coalesce(raw.size_norm, ''), '([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]+)'))[2],
            ''
        )) as size_unit,
        case
            when raw.original_price_curr is not null and raw.original_price_curr > raw.price_original_curr
                 and raw.price_original_curr > 0
            then round((raw.original_price_curr - raw.price_original_curr) / raw.original_price_curr * 100.0, 2)
            else null
        end as raw_discount_pct,
        -- C2 fix: cleaned name preserves package sizes (e.g. "330ml", "500g").
        -- Logic mirrors `pipeline/text_clean.py:clean_name_for_matching()` via
        -- the `clean_product_name` macro so Python + dbt stay in lockstep.
        {{ clean_product_name('raw.name_raw') }} as name_clean
    from raw
    left join exchange er on er.execution_date = raw.scrape_date
)
select
    p.raw_price_id,
    p.item_id,
    p.match_method,
    p.match_confidence,
    p.store_slug,
    p.source_name,
    p.name_raw,
    trim(p.name_clean) as name_clean,
    p.category_native,
    p.brand,
    p.barcode,
    p.size_norm,
    p.currency,
    p.price_original_curr,
    p.original_price_curr,
    p.usd_khr_rate,
    round(p.price_khr::numeric, 2)::numeric(14, 2) as price_khr,
    round(p.original_price_khr::numeric, 2)::numeric(14, 2) as original_price_khr,
    -- Reconcile discount: prefer raw_discount_pct; if absent, derive from original vs current price
    case
        when p.raw_discount_pct is not null then p.raw_discount_pct
        when p.original_price_khr is not null and p.original_price_khr > p.price_khr and p.price_khr > 0
        then round((p.original_price_khr - p.price_khr) / p.original_price_khr * 100.0, 2)
        else 0.00
    end as discount_pct,
    -- on_promo: true if discount >= 1.0% or raw on_promo was set
    case
        when coalesce(p.raw_on_promo, false) then true
        when p.original_price_khr is not null and p.original_price_khr > p.price_khr and p.price_khr > 0
             and ((p.original_price_khr - p.price_khr) / p.original_price_khr * 100.0) >= 1.0
        then true
        else false
    end as on_promo,
    p.size_value,
    case
         when p.size_unit in ('g', 'gm', 'gram', 'grams') then 'g'
         when p.size_unit in ('kg', 'kilo', 'kilos', 'kilogram', 'kilograms') then 'kg'
         when p.size_unit in ('ml', 'millilitre', 'milliliter', 'millilitres', 'milliliters') then 'ml'
         when p.size_unit in ('l', 'ltr', 'litre', 'liter', 'litres', 'liters') then 'l'
         when p.size_unit in ('can', 'cans') then 'can'
         when p.size_unit in ('bottle', 'bottles') then 'bottle'
         when p.size_unit in ('box', 'boxes') then 'box'
         when p.size_unit in ('pack', 'packs', 'pk') then 'pack'
         when p.size_unit in ('bag', 'bags') then 'bag'
         when p.size_unit in ('piece', 'pieces', 'pc', 'pcs') then 'piece'
         when p.size_unit in ('cup', 'cups') then 'cup'
         when p.size_unit in ('bar', 'bars') then 'bar'
         when p.size_unit in ('tube', 'tubes') then 'tube'
         when p.size_unit in ('packet', 'packets', 'pkt') then 'packet'
         when p.size_unit in ('roll', 'rolls') then 'roll'
         when p.size_unit in ('stick', 'sticks') then 'stick'
         when p.size_unit in ('pair', 'pairs') then 'pair'
         when p.size_unit in ('set', 'sets') then 'set'
         when p.size_unit in ('dozen', 'doz') then 'dozen'
         else p.size_unit
    end as size_unit,
    p.pack_qty,
    case
        -- Weight-based unit price (always KHR/kg)
        when p.size_unit in ('kg', 'kilo', 'kilos', 'kilogram', 'kilograms') and p.size_value > 0 
            then p.price_khr / (p.size_value * coalesce(p.pack_qty, 1))
        when p.size_unit in ('g', 'gm', 'gram', 'grams') and p.size_value > 0 
            then p.price_khr / ((p.size_value * coalesce(p.pack_qty, 1)) / 1000.0)
        -- Volume-based unit price (always KHR/l)
        when p.size_unit in ('l', 'ltr', 'litre', 'liter', 'litres', 'liters') and p.size_value > 0 
            then p.price_khr / (p.size_value * coalesce(p.pack_qty, 1))
        when p.size_unit in ('ml', 'millilitre', 'milliliter', 'millilitres', 'milliliters') and p.size_value > 0 
            then p.price_khr / ((p.size_value * coalesce(p.pack_qty, 1)) / 1000.0)
        else null
    end as unit_price_khr,
    -- Outlier detection: flag extreme pricing anomalies or corrupt inputs
    case
        when p.price_khr <= 0 then true
        when p.price_khr > 100000000 then true -- Upper bound for consumer retail item (>100M KHR ~ $25,000 USD)
        when p.original_price_curr is not null and p.price_original_curr > 0 
             and p.price_original_curr > p.original_price_curr * 10 then true
        else false
    end as is_outlier,
    (p.price_khr > 0 and p.price_khr <= 100000000) as cpi_eligible,
    -- Carry through is_fallback flag + operator reason from scraper (raw_payload JSONB)
    coalesce(p.is_fallback_raw::boolean, false) as is_fallback,
    p.fallback_reason,
    p.scrape_date,
    p.scraped_at
from parsed p
