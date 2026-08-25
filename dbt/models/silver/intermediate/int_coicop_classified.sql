-- int_coicop_classified
-- Streamlined AI-First COICOP classification ladder.
-- One row per (item_id, store_slug) from int_prices_cleaned.
--
-- Resolution order (first match wins):
--   1. override_exact -> coicop_override seed + silver.coicop_override_manual
--                        (exact barcode, product_key, or store-tagged rule)
--   2. store_purity   -> single-division stores (pharmacies=06, real estate=04,
--                        hotels=11, transit/fuel=07, telecom=08). Instant O(1)
--   3. override_global-> global name substring rules from coicop_override
--   4. gemini_ai      -> silver.dim_coicop_ai_cache (pre-warmed / persistent Gemini AI cache)
--   5. category_map   -> silver.coicop_category_map (store native category taxonomy fallback)
--   6. store_default  -> coicop_store_defaults seed + UNCLASSIFIED fallback
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['item_id', 'store_slug'],
    on_schema_change='append_new_columns',
    post_hook=[
        "CREATE INDEX IF NOT EXISTS idx_int_coicop_item_store ON {{ this }} (item_id, store_slug)",
        "CREATE INDEX IF NOT EXISTS idx_int_coicop_division ON {{ this }} (coicop_division)"
    ]
) }}

with items as materialized (
    select distinct on (p.item_id, p.store_slug)
        p.item_id::text as item_id,
        p.store_slug,
        ci.canonical_name,
        ci.barcode,
        p.category_native,
        p.item_id::text as product_key,
        null::numeric as price_khr,
        lower(regexp_replace(trim(ci.canonical_name), '\s+', ' ', 'g')) as norm_name,
        lower(trim(coalesce(p.category_native, ''))) as norm_category
    from (
        select distinct item_id, store_slug, category_native
        from {{ ref('int_prices_cleaned') }}
        where item_id is not null
          {% if var('reclassify_all', false) %}
          {% elif var('ds', none) %}
          and scrape_date = '{{ var("ds") }}'::date
          {% else %}
          and scrape_date = (select max(scrape_date) from {{ ref('int_prices_cleaned') }})
          {% endif %}
    ) p
    join {{ source('silver', 'canonical_items') }} ci
        on ci.item_id = p.item_id
    {% if is_incremental() and not var('reclassify_all', false) %}
    where not exists (
        select 1 from {{ this }} t
        where t.item_id = p.item_id::text
          and t.store_slug = p.store_slug
          and t.coicop_method = 'override'
    )
    {% endif %}
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
ov_product_key as materialized (
    select distinct on (match_value)
        match_value as product_key,
        coicop_division
    from all_overrides
    where match_type = 'product_key' and match_value is not null and match_value <> ''
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
store_purity as materialized (
    select
        i.item_id,
        i.store_slug,
        case
            when i.store_slug in ('khmer24', 'realestate') then '04'
            when i.store_slug in ('communitypharma') then '06'
            when i.store_slug in ('sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') then '11'
            when i.store_slug in ('bookmebus', 'redbus', 'redmebus', 'new_gasoline') then '07'
            when i.store_slug in ('arystore', 'samnangshop', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then '08'
        end as purity_division
    from items i
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
cat_map_prejoined as materialized (
    select distinct on (store_slug, lower(trim(category_native)))
        store_slug,
        lower(trim(category_native)) as cat_key,
        lpad(coicop_division, 2, '0') as coicop_division
    from {{ source('silver', 'coicop_category_map') }}
),
store_defaults_prejoined as materialized (
    select distinct on (store_slug)
        store_slug,
        lpad(default_coicop_division, 2, '0') as coicop_division,
        confidence as confidence_score
    from {{ ref('coicop_store_defaults') }}
    where is_active = true
),
items_evaluated as materialized (
    select
        i.item_id,
        i.store_slug,
        i.canonical_name,
        i.barcode,
        i.product_key,
        i.price_khr,
        i.norm_name,
        i.category_native,
        i.norm_category,
        coalesce(ov_b.coicop_division, ov_pk.coicop_division, ov_ns.coicop_division) as ov_exact_div,
        ps.purity_division,
        ov_ng.coicop_division as ov_global_div,
        case
            when split_part(ai.coicop_code, '.', 1) = '11' and i.store_slug not in ('sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') then null
            when split_part(ai.coicop_code, '.', 1) = '04' and i.store_slug in ('communitypharma', 'delishop', 'aeon', 'aeon3', 'samnangshop', 'arystore', 'bookmebus', 'redbus') then null
            when split_part(ai.coicop_code, '.', 1) = '07' and i.store_slug in ('communitypharma', 'khmer24', 'realestate', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') then null
            else ai.coicop_division
        end as ai_div,
        ai.confidence_score as ai_conf,
        ai.coicop_code as ai_code,
        cm.coicop_division as cat_map_div,
        sd.coicop_division as store_default_div,
        sd.confidence_score as store_default_conf
    from items i
    left join store_purity ps on ps.item_id = i.item_id and ps.store_slug = i.store_slug
    left join ai_prejoined ai on ai.norm_name = i.norm_name
    left join ov_barcode ov_b on i.barcode is not null and trim(i.barcode) <> '' and ov_b.barcode = trim(i.barcode)
    left join ov_product_key ov_pk on i.product_key is not null and trim(i.product_key) <> '' and ov_pk.product_key = trim(i.product_key)
    left join ov_name_store ov_ns on ov_ns.store_slug = i.store_slug and position(ov_ns.match_val_lower in lower(i.canonical_name)) > 0
    left join ov_name_global ov_ng on position(ov_ng.match_val_lower in lower(i.canonical_name)) > 0
    left join cat_map_prejoined cm on cm.store_slug = i.store_slug and cm.cat_key = i.norm_category
    left join store_defaults_prejoined sd on sd.store_slug = i.store_slug
)
select
    f.item_id,
    f.store_slug,
    f.canonical_name,
    f.category_native,
    f.product_key,
    f.price_khr,
    coalesce(
        f.ov_exact_div,
        f.purity_division,
        f.ov_global_div,
        case
            when f.ai_div is not null and coalesce(f.ai_conf, 0.90) >= 0.50 then f.ai_div
            when f.ai_div is not null and coalesce(f.ai_conf, 0.90) < 0.50 then 'REVIEW'
        end,
        f.cat_map_div,
        case when f.store_slug in ('khmer24', 'realestate') then '04' end,
        case when f.store_slug in ('communitypharma') then '06' end,
        case when f.store_slug in ('sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') then '11' end,
        case when f.store_slug in ('bookmebus', 'redbus', 'redmebus', 'new_gasoline') then '07' end,
        case when f.store_slug in ('cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then '08' end,
        f.store_default_div,
        'UNCLASSIFIED'
    ) as coicop_division,
    coalesce(
        f.ov_exact_div,
        case
            when f.purity_division is not null then
                case f.purity_division
                    when '06' then '06.1.2'
                    when '04' then '04.1.1'
                    when '11' then '11.2.0'
                    when '07' then case when f.store_slug in ('bookmebus', 'redbus', 'redmebus') then '07.1.2' else '07.2.2' end
                    when '08' then '08.2.0'
                end
        end,
        f.ov_global_div,
        case
            when f.ai_div is not null and coalesce(f.ai_conf, 0.90) >= 0.50 then f.ai_code
        end,
        f.cat_map_div,
        case when f.store_slug in ('khmer24', 'realestate') then '04.1.1' end,
        case when f.store_slug in ('communitypharma') then '06.1.2' end,
        case when f.store_slug in ('sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') then '11.2.0' end,
        case when f.store_slug in ('bookmebus', 'redbus', 'redmebus') then '07.1.2' end,
        case when f.store_slug in ('new_gasoline') then '07.2.2' end,
        case when f.store_slug in ('cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then '08.2.0' end,
        f.store_default_div,
        'UNCLASSIFIED'
    ) as coicop_code,
    case
        when f.ov_exact_div is not null then 'override'
        when f.purity_division is not null then 'store_default'
        when f.ov_global_div is not null then 'override'
        when f.ai_div is not null and coalesce(f.ai_conf, 0.90) >= 0.50 then 'gemini_ai'
        when f.ai_div is not null and coalesce(f.ai_conf, 0.90) < 0.50 then 'gemini_ai_low_conf'
        when f.cat_map_div is not null then 'category_map'
        when f.store_slug in ('khmer24', 'realestate', 'communitypharma', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk', 'bookmebus', 'redbus', 'redmebus', 'new_gasoline', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then 'store_default'
        when f.store_default_div is not null then 'store_default'
        else 'unclassified'
    end as coicop_method,
    case
        when f.ov_exact_div is not null then 1.000
        when f.purity_division is not null then 0.850
        when f.ov_global_div is not null then 1.000
        when f.ai_div is not null and coalesce(f.ai_conf, 0.90) >= 0.50 then coalesce(f.ai_conf, 0.900)
        when f.ai_div is not null and coalesce(f.ai_conf, 0.90) < 0.50 then 0.400
        when f.cat_map_div is not null then 0.900
        when f.store_slug in ('khmer24', 'realestate', 'communitypharma', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk', 'bookmebus', 'redbus', 'redmebus', 'new_gasoline', 'cellcard', 'cellcard_wifi', 'smart', 'smart_wifi') then 0.850
        when f.store_default_div is not null then coalesce(f.store_default_conf, 0.800)
        else 0.000
    end as coicop_confidence
from items_evaluated f
