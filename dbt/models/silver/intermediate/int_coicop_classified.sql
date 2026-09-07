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
          {% elif var('ds', '') and var('ds') != 'None' and var('ds') != 'null' and var('ds') != 'none' %}
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
          and t.coicop_method not in ('unclassified', 'gemini_ai_low_conf')
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
    order by lower(regexp_replace(trim(product_name), '\s+', ' ', 'g')), classified_at desc
),
cat_map_prejoined as materialized (
    select distinct on (store_slug, lower(trim(category_native)))
        store_slug,
        lower(trim(category_native)) as cat_key,
        lpad(coicop_division, 2, '0') as coicop_division
    from {{ source('silver', 'coicop_category_map') }}
),
cat_map_match as materialized (
    select distinct on (i.item_id, i.store_slug)
        i.item_id,
        i.store_slug,
        cm.coicop_division
    from items i
    join cat_map_prejoined cm on cm.store_slug = i.store_slug and (
        cm.cat_key = i.norm_category
        or cm.cat_key = trim(split_part(i.norm_category, '>', 1))
        or cm.cat_key = trim(split_part(i.norm_category, '/', 1))
    )
    order by i.item_id, i.store_slug,
        case when cm.cat_key = i.norm_category then 1 else 2 end asc
),
text_rules_prejoined as materialized (
    select
        rule_id,
        lpad(coicop_division, 2, '0') as coicop_division,
        pattern,
        negative_pattern,
        priority,
        confidence as confidence_score
    from {{ ref('coicop_text_rules') }}
    where is_active = true
),
text_rule_match as materialized (
    select distinct on (i.item_id, i.store_slug)
        i.item_id,
        i.store_slug,
        r.coicop_division as text_rule_div,
        {{ coicop_code_from_division('r.coicop_division') }} as text_rule_code,
        r.confidence_score as text_rule_conf
    from items i
    join text_rules_prejoined r
      on i.norm_name ~* r.pattern
     and (r.negative_pattern is null or i.norm_name !~* r.negative_pattern)
     and not (r.coicop_division = '11' and i.store_slug not in ('sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk'))
     and not (r.coicop_division = '07' and i.store_slug in ('communitypharma', 'delishop', 'arystore', 'samnangshop', 'khmer24', 'realestate', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk'))
     and not (r.coicop_division = '06' and i.store_slug in ('aeon', 'aeon3'))
     and not (r.coicop_division = '04' and i.store_slug in ('communitypharma', 'delishop', 'aeon', 'aeon3', 'samnangshop', 'arystore', 'bookmebus', 'redbus'))
    order by i.item_id, i.store_slug, r.priority asc
),
store_defaults_prejoined as materialized (
    select distinct on (store_slug)
        store_slug,
        lpad(default_coicop_division, 2, '0') as coicop_division,
        -- P3 #125 — default code when one is supplied; falls back to NULL
        -- and the macro's coicop_code_from_division() expansion kicks in.
        nullif(default_coicop_code, '') as coicop_code,
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
            when split_part(ai.coicop_code, '.', 1) = '07' and i.store_slug in ('communitypharma', 'delishop', 'arystore', 'samnangshop', 'khmer24', 'realestate', 'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk') then null
            else ai.coicop_division
        end as ai_div,
        ai.confidence_score as ai_conf,
        ai.coicop_code as ai_code,
        cm.coicop_division as cat_map_div,
        -- P3 #125: cat_map_code is the only known override is '09' -> '09.5.4';
        -- absent a per-row 5-digit code from coicop_category_map, the macro uses
        -- the 2-digit → 5-digit default table.
        null::varchar as cat_map_code,
        tr.text_rule_div,
        tr.text_rule_code,
        tr.text_rule_conf,
        sd.coicop_division as store_default_div,
        sd.coicop_code as store_default_code,
        sd.confidence_score as store_default_conf
    from items i
    left join store_purity ps on ps.item_id = i.item_id and ps.store_slug = i.store_slug
    left join ai_prejoined ai on ai.norm_name = i.norm_name
    left join ov_barcode ov_b on i.barcode is not null and trim(i.barcode) <> '' and ov_b.barcode = trim(i.barcode)
    left join ov_product_key ov_pk on i.product_key is not null and trim(i.product_key) <> '' and ov_pk.product_key = trim(i.product_key)
    left join ov_name_store ov_ns on ov_ns.store_slug = i.store_slug and position(ov_ns.match_val_lower in i.norm_name) > 0
    left join ov_name_global ov_ng on position(ov_ng.match_val_lower in i.norm_name) > 0
    left join cat_map_match cm on cm.item_id = i.item_id and cm.store_slug = i.store_slug
    left join text_rule_match tr on tr.item_id = i.item_id and tr.store_slug = i.store_slug
    left join store_defaults_prejoined sd on sd.store_slug = i.store_slug
)
select
    f.item_id,
    f.store_slug,
    f.canonical_name,
    f.category_native,
    f.product_key,
    f.price_khr,
    {{ resolve_coicop_division(
        'f.ov_exact_div', 'f.purity_division', 'f.ov_global_div',
        'f.ai_div', 'f.ai_conf',
        'f.cat_map_div', 'f.text_rule_div',
        'f.store_default_div', 'f.store_slug') }} as coicop_division,
    {{ resolve_coicop_code(
        'f.ai_div', 'f.ai_code', 'f.ai_conf',
        'f.purity_division', 'f.store_slug',
        'f.ov_exact_div', 'f.ov_global_div',
        'f.cat_map_div', 'f.cat_map_code',
        'f.text_rule_div', 'f.text_rule_code',
        'f.store_default_div', 'f.store_default_code') }} as coicop_code,
    {{ resolve_coicop_method(
        'f.ov_exact_div', 'f.purity_division', 'f.ov_global_div',
        'f.ai_div', 'f.ai_conf',
        'f.cat_map_div', 'f.text_rule_div',
        'f.store_slug', 'f.store_default_div') }} as coicop_method,
    {{ resolve_coicop_confidence(
        'f.ov_exact_div', 'f.purity_division', 'f.ov_global_div',
        'f.ai_div', 'f.ai_conf',
        'f.cat_map_div', 'f.text_rule_div', 'f.text_rule_conf',
        'f.store_slug', 'f.store_default_div', 'f.store_default_conf') }} as coicop_confidence
from items_evaluated f
