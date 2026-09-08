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
all_overrides as (
    select match_type, trim(match_value) as match_value, lower(trim(match_value)) as match_val_lower, store_slug, lpad(coicop_division, 2, '0') as coicop_division
    from {{ ref('coicop_override') }}
    union all
    select match_type, trim(match_value) as match_value, lower(trim(match_value)) as match_val_lower, store_slug, lpad(coicop_division, 2, '0') as coicop_division
    from {{ source('silver', 'coicop_override_manual') }}
),
ov_barcode as (
    select distinct on (match_value)
        match_value as barcode,
        coicop_division
    from all_overrides
    where match_type = 'barcode' and match_value is not null and match_value <> ''
),
ov_name_store as (
    select distinct on (store_slug, match_val_lower)
        match_val_lower, store_slug, coicop_division
    from all_overrides
    where match_type = 'name' and store_slug is not null and store_slug <> ''
),
ov_name_global as (
    select distinct on (match_val_lower)
        match_val_lower, coicop_division
    from all_overrides
    where match_type = 'name' and (store_slug is null or store_slug = '')
),
ov_name_store_match as (
    select distinct on (p.raw_price_id)
        p.raw_price_id,
        ov.coicop_division
    from cleaned_prices p
    join ov_name_store ov on ov.store_slug = p.store_slug and position(ov.match_val_lower in p.name_clean_lower) > 0
    where p.store_slug in (select store_slug from ov_name_store)
    order by p.raw_price_id, length(ov.match_val_lower) desc
),
ov_name_global_match as (
    select distinct on (p.raw_price_id)
        p.raw_price_id,
        ov.coicop_division
    from cleaned_prices p
    join ov_name_global ov on position(ov.match_val_lower in p.name_clean_lower) > 0
    order by p.raw_price_id, length(ov.match_val_lower) desc
),
ai_prejoined as (
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
    order by lower(regexp_replace(trim(product_name), '\s+', ' ', 'g')), classified_at desc
),
ai_match as (
    select distinct on (p.raw_price_id)
        p.raw_price_id,
        ai.coicop_division,
        ai.coicop_code,
        ai.confidence_score
    from cleaned_prices p
    join ai_prejoined ai on ai.norm_name = p.norm_name
    order by p.raw_price_id, ai.confidence_score desc
),
cat_map_prejoined as (
    select distinct on (store_slug, lower(trim(category_native)))
        store_slug,
        lower(trim(category_native)) as cat_key,
        lpad(coicop_division, 2, '0') as coicop_division
    from {{ source('silver', 'coicop_category_map') }}
),
cat_map_match as (
    select distinct on (p.raw_price_id)
        p.raw_price_id,
        cm.coicop_division
    from cleaned_prices p
    join cat_map_prejoined cm
        on cm.store_slug = p.store_slug and (
            cm.cat_key = p.norm_category
            or cm.cat_key = trim(split_part(p.norm_category, '>', 1))
            or cm.cat_key = trim(split_part(p.norm_category, '/', 1))
        )
    order by p.raw_price_id,
        case when cm.cat_key = p.norm_category then 1 else 2 end asc
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
        coalesce(
            ov_b.coicop_division,
            ov_ns.coicop_division,
            case
                when p.store_slug in ('khmer24', 'realestate', 'edc', 'ppwsa') then '04'
                when p.store_slug in ('communitypharma') then '06'
                when p.store_slug in ('sokhahotel', 'hyyathotel', 'hyatthotel', 'hyatt', 'bayonbkk') then '11'
                when p.store_slug in ('bookmebus', 'redbus', 'redmebus', 'new_gasoline', 'khmermoto') then '07'
                when p.store_slug in ('arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi', 'metfone') then '08'
            end,
            ov_ng.coicop_division,
            case when c.coicop_method <> 'store_default' then c.coicop_division end,
            case
                when ai.coicop_division is not null and coalesce(ai.confidence_score, 0.90) >= 0.50 then
                    case
                        when split_part(ai.coicop_code, '.', 1) = '11' and p.store_slug not in ('sokhahotel', 'hyyathotel', 'hyatthotel', 'hyatt', 'bayonbkk') then null
                        when split_part(ai.coicop_code, '.', 1) = '04' and p.store_slug in ('communitypharma', 'delishop', 'aeon', 'aeon3', 'samnangshop', 'arystore', 'bookmebus', 'redbus') then null
                        when split_part(ai.coicop_code, '.', 1) = '07' and p.store_slug in ('communitypharma', 'khmer24', 'realestate', 'sokhahotel', 'hyyathotel', 'hyatthotel', 'hyatt', 'bayonbkk') then null
                        else ai.coicop_division
                    end
            end,
            cm.coicop_division,
            c.coicop_division,
            case
                when p.store_slug in ('delishop', 'aeon', 'grab_lucky', 'grab_chipmong') then '01'
                when p.store_slug in ('grab_ucare') then '06'
                when p.store_slug in ('aeon3') then '03'
                when p.store_slug in ('l192') then '05'
            end,
            'UNCLASSIFIED'
        ) as coicop_division,
        case
            when coalesce(ov_b.coicop_division, ov_ns.coicop_division) is not null then
                {{ coicop_code_from_division("coalesce(ov_b.coicop_division, ov_ns.coicop_division)") }}
            when p.store_slug in ('khmer24', 'realestate') then '04.1.1'
            when p.store_slug = 'edc' then '04.5.1'
            when p.store_slug = 'ppwsa' then '04.4.1'
            when p.store_slug in ('communitypharma') then '06.1.2'
            when p.store_slug in ('sokhahotel', 'hyyathotel', 'hyatthotel', 'hyatt') then '11.2.0'
            when p.store_slug = 'bayonbkk' then '11.1.1'
            when p.store_slug in ('bookmebus', 'redbus', 'redmebus') then '07.3.1'
            when p.store_slug = 'new_gasoline' then '07.2.2'
            when p.store_slug = 'khmermoto' then '07.1.2'
            when p.store_slug in ('cellcard', 'cellcard_wifi', 'smart', 'smart_wifi', 'metfone') then '08.3.0'
            when p.store_slug in ('arystore', 'samnangshop') then '08.2.0'
            when ov_ng.coicop_division is not null then
                {{ coicop_code_from_division("ov_ng.coicop_division") }}
            when c.coicop_division is not null and c.coicop_method <> 'store_default'
                 and c.coicop_code is not null and c.coicop_code ~ '^\d{2}\.\d{1,2}\.\d{1,2}$'
                 and lpad(split_part(c.coicop_code, '.', 1), 2, '0') = c.coicop_division
                 then c.coicop_code
            when ai.coicop_division is not null and coalesce(ai.confidence_score, 0.90) >= 0.50
                 and not (split_part(ai.coicop_code, '.', 1) = '11' and p.store_slug not in ('sokhahotel', 'hyyathotel', 'hyatthotel', 'hyatt', 'bayonbkk'))
                 and not (split_part(ai.coicop_code, '.', 1) = '04' and p.store_slug in ('communitypharma', 'delishop', 'aeon', 'aeon3', 'samnangshop', 'arystore', 'bookmebus', 'redbus'))
                 and not (split_part(ai.coicop_code, '.', 1) = '07' and p.store_slug in ('communitypharma', 'khmer24', 'realestate', 'sokhahotel', 'hyyathotel', 'hyatthotel', 'hyatt', 'bayonbkk')) then
                case
                    when ai.coicop_code is not null and ai.coicop_code ~ '^\d{2}\.\d{1,2}\.\d{1,2}$'
                         and lpad(split_part(ai.coicop_code, '.', 1), 2, '0') = ai.coicop_division
                        then ai.coicop_code
                    else {{ coicop_code_from_division("ai.coicop_division") }}
                end
            when cm.coicop_division is not null then
                {{ coicop_code_from_division("cm.coicop_division") }}
            when c.coicop_code is not null and c.coicop_code ~ '^\d{2}\.\d{1,2}\.\d{1,2}$'
                 and lpad(split_part(c.coicop_code, '.', 1), 2, '0') = c.coicop_division then c.coicop_code
            when p.store_slug in ('grab_ucare') then '06.1.2'
            when p.store_slug in ('delishop', 'aeon', 'grab_lucky', 'grab_chipmong') then '01.1.1'
            when p.store_slug in ('aeon3') then '03.1.2'
            when p.store_slug in ('l192') then '05.1.1'
            else '01.1.1'
        end as coicop_code,
        case
            when ov_b.coicop_division is not null or ov_ns.coicop_division is not null then 'override'
            when p.store_slug in (
                'khmer24', 'realestate', 'communitypharma', 'sokhahotel', 'hyyathotel', 'hyatthotel', 'hyatt', 'bayonbkk',
                'bookmebus', 'redbus', 'redmebus', 'new_gasoline', 'arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi', 'metfone', 'khmermoto', 'edc', 'ppwsa'
            ) then 'store_purity'
            when ov_ng.coicop_division is not null then 'override'
            when c.coicop_division is not null and c.coicop_method <> 'store_default' then c.coicop_method
            when c.coicop_method is not null and c.coicop_method <> 'store_default' then c.coicop_method
            when p.store_slug in ('khmer24', 'realestate', 'communitypharma', 'sokhahotel', 'hyyathotel', 'hyatthotel', 'hyatt', 'bayonbkk', 'bookmebus', 'redbus', 'redmebus', 'new_gasoline', 'arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi', 'metfone', 'khmermoto', 'edc', 'ppwsa') then 'store_default'
            when ai.coicop_division is not null and coalesce(ai.confidence_score, 0.90) >= 0.50 then 'gemini_ai'
            when cm.coicop_division is not null then 'category_map'
            when c.coicop_method is not null then c.coicop_method
            else 'store_default'
        end as coicop_method,
        coalesce(
            c.coicop_confidence,
            case
                when ov_b.coicop_division is not null or ov_ns.coicop_division is not null or ov_ng.coicop_division is not null then 1.000
                when p.store_slug in ('khmer24', 'realestate', 'communitypharma', 'sokhahotel', 'hyyathotel', 'bayonbkk', 'bookmebus', 'redbus', 'new_gasoline', 'arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi', 'metfone', 'khmermoto', 'edc', 'ppwsa', 'aeon3', 'delishop', 'aeon', 'l192', 'grab_ucare', 'grab_lucky', 'grab_chipmong') then 0.850
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
    left join cat_map_match cm
        on cm.raw_price_id = p.raw_price_id
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
