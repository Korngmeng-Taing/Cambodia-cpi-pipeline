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

with cleaned_prices as (
    select * from {{ ref('int_prices_cleaned') }}
    {% if is_incremental() %}
        {% if var('ds', '') and var('ds') != 'None' and var('ds') != 'null' and var('ds') != 'none' %}
            where scrape_date = '{{ var("ds") }}'::date
        {% else %}
            where scrape_date >= (select coalesce(max(scrape_date) - interval '2 days', '2020-01-01'::date) from {{ this }})
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
all_overrides as materialized (
    select match_type, trim(match_value) as match_value, lower(trim(match_value)) as match_val_lower, store_slug, lpad(coicop_division, 2, '0') as coicop_division
    from {{ ref('coicop_override') }}
    union all
    select match_type, trim(match_value) as match_value, lower(trim(match_value)) as match_val_lower, store_slug, lpad(coicop_division, 2, '0') as coicop_division
    from {{ source('silver', 'coicop_override_manual') }}
),
ov_barcode as materialized (
    select distinct on (match_value)
        match_value as barcode,
        coicop_division
    from all_overrides
    where match_type = 'barcode' and match_value is not null and match_value <> ''
),
ov_name_store as materialized (
    select distinct on (store_slug, match_val_lower)
        match_val_lower, store_slug, coicop_division
    from all_overrides
    where match_type = 'name' and store_slug is not null and store_slug <> ''
),
ov_name_global as materialized (
    select distinct on (match_val_lower)
        match_val_lower, coicop_division
    from all_overrides
    where match_type = 'name' and (store_slug is null or store_slug = '')
),
ov_name_store_match as materialized (
    select distinct on (p.raw_price_id)
        p.raw_price_id,
        ov.coicop_division
    from cleaned_prices p
    join ov_name_store ov on ov.store_slug = p.store_slug and position(ov.match_val_lower in lower(p.name_clean)) > 0
    order by p.raw_price_id, length(ov.match_val_lower) desc
),
ov_name_global_match as materialized (
    select distinct on (p.raw_price_id)
        p.raw_price_id,
        ov.coicop_division
    from cleaned_prices p
    join ov_name_global ov on position(ov.match_val_lower in lower(p.name_clean)) > 0
    order by p.raw_price_id, length(ov.match_val_lower) desc
),
ai_prejoined as materialized (
    select distinct on (lower(regexp_replace(trim(product_name), '\s+', ' ', 'g')))
        lower(regexp_replace(trim(product_name), '\s+', ' ', 'g')) as norm_name,
        coicop_code,
        case
            when split_part(coicop_code, '.', 1) in ('12', '13') then '12'
            else lpad(split_part(coicop_code, '.', 1), 2, '0')
        end as coicop_division,
        confidence_score
    from {{ source('silver', 'dim_coicop_ai_cache') }}
    where coicop_code <> '99.9.9'
),
ai_match as materialized (
    select distinct on (p.raw_price_id)
        p.raw_price_id,
        ai.coicop_division,
        ai.coicop_code,
        ai.confidence_score
    from cleaned_prices p
    join ai_prejoined ai on ai.norm_name = lower(regexp_replace(trim(p.name_clean), '\s+', ' ', 'g'))
    order by p.raw_price_id, ai.confidence_score desc
),
cat_map_prejoined as materialized (
    select distinct on (store_slug, lower(trim(category_native)))
        store_slug,
        lower(trim(category_native)) as cat_key,
        lpad(coicop_division, 2, '0') as coicop_division
    from {{ source('silver', 'coicop_category_map') }}
)

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
    coalesce(
        c.coicop_division,
        ov_b.coicop_division,
        ov_ns.coicop_division,
        case
            when p.store_slug in ('khmer24', 'realestate') then '04'
            when p.store_slug in ('communitypharma') then '06'
            when p.store_slug in ('sokhahotel', 'hyyathotel', 'bayonbkk') then '11'
            when p.store_slug in ('bookmebus', 'redbus', 'new_gasoline') then '07'
            when p.store_slug in ('arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then '08'
        end,
        ov_ng.coicop_division,
        case
            when ai.coicop_division is not null and coalesce(ai.confidence_score, 0.90) >= 0.50 then
                case
                    when split_part(ai.coicop_code, '.', 1) = '11' and p.store_slug not in ('sokhahotel', 'hyyathotel', 'bayonbkk') then null
                    when split_part(ai.coicop_code, '.', 1) = '04' and p.store_slug in ('communitypharma', 'delishop', 'aeon', 'aeon3', 'samnangshop', 'arystore', 'bookmebus', 'redbus') then null
                    when split_part(ai.coicop_code, '.', 1) = '07' and p.store_slug in ('communitypharma', 'khmer24', 'realestate', 'sokhahotel', 'hyyathotel', 'bayonbkk') then null
                    else ai.coicop_division
                end
        end,
        cm.coicop_division,
        case
            when p.store_slug in ('delishop', 'aeon') then '01'
            when p.store_slug in ('aeon3') then '03'
            when p.store_slug in ('l192') then '05'
        end,
        'UNCLASSIFIED'
    ) as coicop_division,
    case
        when c.coicop_code is not null and c.coicop_code ~ '^\d{2}\.\d{1,2}\.\d{1,2}$' then c.coicop_code
        when c.coicop_code is not null and c.coicop_code <> '' and c.coicop_code <> 'UNCLASSIFIED' then c.coicop_code
        when coalesce(ov_b.coicop_division, ov_ns.coicop_division, ov_ng.coicop_division) is not null then
            case coalesce(ov_b.coicop_division, ov_ns.coicop_division, ov_ng.coicop_division)
                when '01' then '01.1.1'
                when '02' then '02.1.1'
                when '03' then '03.1.2'
                when '04' then '04.1.1'
                when '05' then '05.1.1'
                when '06' then '06.1.1'
                when '07' then '07.2.2'
                when '08' then '08.2.0'
                when '09' then '09.1.1'
                when '10' then '10.4.1'
                when '11' then '11.1.1'
                when '12' then '12.1.1'
                else '01.1.1'
            end
        when ai.coicop_code is not null and ai.coicop_code ~ '^\d{2}\.\d{1,2}\.\d{1,2}$' then ai.coicop_code
        when cm.coicop_division is not null then
            case cm.coicop_division
                when '01' then '01.1.1'
                when '02' then '02.1.1'
                when '03' then '03.1.2'
                when '04' then '04.1.1'
                when '05' then '05.1.1'
                when '06' then '06.1.1'
                when '07' then '07.2.2'
                when '08' then '08.2.0'
                when '09' then '09.5.4'
                when '10' then '10.4.1'
                when '11' then '11.1.1'
                when '12' then '12.1.1'
                else '01.1.1'
            end
        when p.store_slug in ('khmer24', 'realestate') then '04.1.1'
        when p.store_slug in ('communitypharma') then '06.1.2'
        when p.store_slug in ('sokhahotel', 'hyyathotel') then '11.2.0'
        when p.store_slug in ('bayonbkk') then '11.1.1'
        when p.store_slug in ('bookmebus', 'redbus') then '07.3.1'
        when p.store_slug in ('new_gasoline') then '07.2.2'
        when p.store_slug in ('cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then '08.3.0'
        when p.store_slug in ('arystore', 'samnangshop') then '08.2.0'
        when p.store_slug in ('delishop', 'aeon') then '01.1.1'
        when p.store_slug in ('aeon3') then '03.1.2'
        when p.store_slug in ('l192') then '05.1.1'
        else 'UNCLASSIFIED'
    end as coicop_code,
    coalesce(
        c.coicop_method,
        case
            when ov_b.coicop_division is not null or ov_ns.coicop_division is not null or ov_ng.coicop_division is not null then 'override'
            when p.store_slug in ('khmer24', 'realestate', 'communitypharma', 'sokhahotel', 'hyyathotel', 'bayonbkk', 'bookmebus', 'redbus', 'new_gasoline', 'arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then 'store_default'
            when ai.coicop_division is not null and coalesce(ai.confidence_score, 0.90) >= 0.50 then 'gemini_ai'
            when cm.coicop_division is not null then 'category_map'
            else 'store_default'
        end
    ) as coicop_method,
    coalesce(
        c.coicop_confidence,
        case
            when ov_b.coicop_division is not null or ov_ns.coicop_division is not null or ov_ng.coicop_division is not null then 1.000
            when p.store_slug in ('khmer24', 'realestate', 'communitypharma', 'sokhahotel', 'hyyathotel', 'bayonbkk', 'bookmebus', 'redbus', 'new_gasoline', 'arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then 0.850
            when ai.coicop_division is not null and coalesce(ai.confidence_score, 0.90) >= 0.50 then coalesce(ai.confidence_score, 0.900)
            when cm.coicop_division is not null then 0.900
            else 0.800
        end
    ) as coicop_confidence,
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
left join ov_barcode ov_b
    on p.barcode is not null and trim(p.barcode) <> '' and ov_b.barcode = trim(p.barcode)
left join ov_name_store_match ov_ns
    on ov_ns.raw_price_id = p.raw_price_id
left join ov_name_global_match ov_ng
    on ov_ng.raw_price_id = p.raw_price_id
left join ai_match ai
    on ai.raw_price_id = p.raw_price_id
left join cat_map_prejoined cm
    on cm.store_slug = p.store_slug and cm.cat_key = lower(trim(coalesce(p.category_native, '')))
-- C2 fix: exclude NULL/zero prices to prevent corrupting Jevons index calculations
where p.price_khr is not null and p.price_khr > 0
