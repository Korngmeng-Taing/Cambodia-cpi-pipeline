-- stg_raw_scrapes
-- Unpacks staging.raw_scrapes.payload (JSONB array of canonical Schema v1.0
-- records) into one row per observation.
{{ config(materialized='view') }}

select
    rs.scrape_date,
    rs.store_slug,
    rs.source_type,
    rs.run_id,
    rs.created_at as batch_created_at,
    r.value ->> 'item_id'         as item_id,
    r.value ->> 'store'           as store_name,
    r.value ->> 'name'            as name,
    (r.value ->> 'price')::numeric as price,
    r.value ->> 'currency'        as currency,
    (r.value ->> 'original_price')::numeric as original_price,
    r.value ->> 'barcode'         as barcode,
    r.value ->> 'brand'           as brand,
    r.value ->> 'category_native' as category_native,
    r.value ->> 'package_size'    as package_size,
    r.value ->> 'unit'            as unit,
    r.value ->> 'url'             as url,
    r.value ->> 'image_url'       as image_url,
    (r.value ->> 'is_fallback')::boolean as is_fallback,
    r.value -> 'attrs'            as attrs
from {{ source('staging', 'raw_scrapes') }} rs
cross join lateral jsonb_array_elements(
    case when jsonb_typeof(rs.payload) = 'array' then rs.payload else '[]'::jsonb end
) as r(value)
