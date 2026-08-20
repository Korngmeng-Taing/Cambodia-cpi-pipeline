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
    unique_key='raw_price_id',
    on_schema_change='append_new_columns'
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
        (rp.raw_payload ->> 'original_price')::numeric as original_price_curr,
        rp.price as price_original_curr,
        rp.currency,
        rp.scraped_at,
        rp.scraped_at::date as scrape_date
    from {{ source('bronze', 'raw_prices') }} rp
    left join {{ source('silver', 'item_match_log') }} iml
        on iml.raw_price_id = rp.raw_price_id
    {% if is_incremental() %}
        {% if var('ds', '') != '' %}
            where rp.scraped_at::date = '{{ var("ds") }}'::date
        {% else %}
            where rp.scraped_at::date >= (select coalesce(max(scrape_date) - interval '2 days', '2020-01-01'::date) from {{ this }})
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
        coalesce((regexp_match(coalesce(raw.size_norm, ''), '[0-9]+(?:\.[0-9]+)?'))[1], null)::numeric as size_value,
        lower(coalesce((regexp_match(coalesce(raw.size_norm, ''), '[a-zA-Z]+'))[1], '')) as size_unit,
        case
            when raw.original_price_curr is not null and raw.original_price_curr > raw.price_original_curr
                 and raw.price_original_curr > 0
            then round((raw.original_price_curr - raw.price_original_curr) / raw.original_price_curr * 100.0, 2)
            else null
        end as raw_discount_pct,
        -- Text cleaning: Khmer-aware expansion + uppercase + strip HTML entities + strip promo words + strip prices + collapse whitespace
        upper(
            regexp_replace(
                regexp_replace(
                    regexp_replace(
                        regexp_replace(
                            regexp_replace(
                                regexp_replace(
                                    regexp_replace(
                                        regexp_replace(
                                            regexp_replace(
                                                translate(
                                                    regexp_replace(
                                                        regexp_replace(
                                                            regexp_replace(
                                                                regexp_replace(raw.name_raw, '&amp;|&#39;|&lt;|&gt;|&quot;', ' ', 'g'),
                                                                '[$\u17DB]?\s*\d{1,3}(?:[,.\s]\d{3})*(?:[.,]\d{1,2})?\s*(?:KHR|USD|RIEL|\$)?', ' ', 'g'
                                                            ),
                                                            '\b(SALE|PROMO|PROMOTION|DISCOUNT|CLEARANCE|HOT\s*DEAL|BEST\s*SELLER|NEW\s*ARRIVAL|LIMITED|SPECIAL\s*OFFER|FLASH\s*SALE|FREE\s*SHIPPING|BUNDLE)\b', ' ', 'gi'
                                                        ),
                                                        '\s+', ' '
                                                    ),
                                                    '០១២៣៤៥៦៧៨៩', '0123456789'
                                                ),
                                                'សាំង', 'GASOLINE', 'g'
                                            ),
                                            'ស្រា', 'BEER', 'g'
                                        ),
                                        'អង្គរ', 'RICE', 'g'
                                    ),
                                    'ត្រី', 'FISH', 'g'
                                ),
                                'ទឹក', 'WATER', 'g'
                            ),
                            'មាន់', 'CHICKEN', 'g'
                        ),
                        'ជ្រូក', 'PORK', 'g'
                    ),
                    'គោ', 'BEEF', 'g'
                ),
                '\s+', ' ', 'g'
            )
        ) as name_clean
    from raw
    left join exchange er on er.execution_date = raw.scrape_date
),
with_price_stats as (
    select
        p.*,
        avg(p.price_khr) over () as avg_price_all,
        stddev_samp(p.price_khr) over () as stddev_price_all,
        avg(p.price_khr) over (partition by p.store_slug) as avg_price_store,
        stddev_samp(p.price_khr) over (partition by p.store_slug) as stddev_price_store
    from parsed p
)
select
    wps.raw_price_id,
    wps.item_id,
    wps.match_method,
    wps.match_confidence,
    wps.store_slug,
    wps.source_name,
    wps.name_raw,
    trim(wps.name_clean) as name_clean,
    wps.category_native,
    wps.brand,
    wps.barcode,
    wps.size_norm,
    wps.currency,
    wps.price_original_curr,
    wps.original_price_curr,
    wps.usd_khr_rate,
    round(wps.price_khr, 2) as price_khr,
    round(wps.original_price_khr, 2) as original_price_khr,
    case
        when wps.raw_discount_pct is null then null
        when wps.raw_discount_pct < 0 then 0.00
        when wps.raw_discount_pct > 95 then 95.00
        else wps.raw_discount_pct
    end as discount_pct,
    (wps.original_price_curr is not null
        and wps.original_price_curr > wps.price_original_curr) as on_promo,
    wps.size_value,
    -- Expanded unit normalization: g, ml, l, kg + pack, can, bottle, box, piece, pcs, etc.
    case when wps.size_unit in ('g', 'gm', 'gram', 'grams') then 'g'
         when wps.size_unit in ('ml', 'millilitre', 'milliliter', 'millilitres', 'milliliters') then 'ml'
         when wps.size_unit in ('l', 'ltr', 'litre', 'liter', 'litres', 'liters') then 'l'
         when wps.size_unit in ('kg', 'kilo', 'kilos', 'kilogram', 'kilograms') then 'kg'
         when wps.size_unit in ('pack', 'pk', 'pks', 'packs') then 'pack'
         when wps.size_unit in ('can', 'cans') then 'can'
         when wps.size_unit in ('bottle', 'bottles', 'btl', 'btls') then 'bottle'
         when wps.size_unit in ('box', 'boxes', 'bx') then 'box'
         when wps.size_unit in ('pcs', 'piece', 'pieces', 'pc', 'pce') then 'piece'
         when wps.size_unit in ('sachet', 'sachets', 'sac') then 'sachet'
         when wps.size_unit in ('bag', 'bags') then 'bag'
         when wps.size_unit in ('carton', 'cartons') then 'carton'
         when wps.size_unit in ('jar', 'jars') then 'jar'
         when wps.size_unit in ('tube', 'tubes') then 'tube'
         when wps.size_unit in ('packet', 'packets', 'pkt') then 'packet'
         when wps.size_unit in ('roll', 'rolls') then 'roll'
         when wps.size_unit in ('stick', 'sticks') then 'stick'
         when wps.size_unit in ('pair', 'pairs') then 'pair'
         when wps.size_unit in ('set', 'sets') then 'set'
         when wps.size_unit in ('dozen', 'doz') then 'dozen'
         else wps.size_unit
    end as size_unit,
    1 as pack_qty,
    case
        -- Weight-based unit price (always KHR/kg)
        when wps.size_unit in ('kg', 'kilo', 'kilos', 'kilogram', 'kilograms') and wps.size_value > 0 then wps.price_khr / wps.size_value
        when wps.size_unit in ('g', 'gm', 'gram', 'grams') and wps.size_value > 0 then wps.price_khr / (wps.size_value / 1000.0)
        -- Volume-based unit price (always KHR/l)
        when wps.size_unit in ('l', 'ltr', 'litre', 'liter', 'litres', 'liters') and wps.size_value > 0 then wps.price_khr / wps.size_value
        when wps.size_unit in ('ml', 'millilitre', 'milliliter', 'millilitres', 'milliliters') and wps.size_value > 0 then wps.price_khr / (wps.size_value / 1000.0)
        else null
    end as unit_price_khr,
    -- Outlier detection: flag prices >3 stddev from the store-level mean
    case
        when wps.price_khr > 0
             and wps.stddev_price_store > 0
             and wps.price_khr > wps.avg_price_store + 3 * wps.stddev_price_store
        then true
        when wps.price_khr > 0
             and wps.stddev_price_store > 0
             and wps.price_khr < wps.avg_price_store - 3 * wps.stddev_price_store
        then true
        else false
    end as is_outlier,
    (wps.price_khr > 0 and wps.price_khr <= 100000000) as cpi_eligible,
    -- Carry through is_fallback flag from scraper (raw_payload JSONB)
    coalesce(wps.is_fallback_raw::boolean, false) as is_fallback,
    wps.scrape_date,
    wps.scraped_at
from with_price_stats wps
