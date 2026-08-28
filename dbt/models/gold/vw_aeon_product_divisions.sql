-- vw_aeon_product_divisions
-- Gold Layer View: AEON multi-category product distribution across COICOP divisions
-- Created for easy querying of AEON product classifications
{{ config(
    materialized='view'
) }}

with classified_products as (
    select
        ci.item_id,
        ci.canonical_name,
        ci.brand,
        ci.barcode,
        ci.size_norm,
        coalesce(cs.coicop_division, 'UNCLASSIFIED') as coicop_division,
        coalesce(cs.coicop_code, cs.coicop_division, 'UNCLASSIFIED') as coicop_code,
        case
            when cs.coicop_division = '01' then 'Food & Non-Alcoholic Beverages'
            when cs.coicop_division = '02' then 'Alcoholic Beverages & Tobacco'
            when cs.coicop_division = '03' then 'Clothing & Footwear'
            when cs.coicop_division = '04' then 'Housing, Water, Electricity, Gas'
            when cs.coicop_division = '05' then 'Furnishings, Household Equipment'
            when cs.coicop_division = '06' then 'Health'
            when cs.coicop_division = '07' then 'Transport'
            when cs.coicop_division = '08' then 'Communication'
            when cs.coicop_division = '09' then 'Recreation & Culture'
            when cs.coicop_division = '10' then 'Education'
            when cs.coicop_division = '11' then 'Restaurants & Hotels'
            when cs.coicop_division = '12' then 'Miscellaneous Goods & Services'
            else 'UNCLASSIFIED'
        end as division_name,
        fdp.store_slug,
        fdp.scrape_date,
        fdp.unit_price_local,
        fdp.currency
    from {{ source('silver', 'canonical_items') }} ci
    left join (
        select distinct on (item_id::uuid)
            item_id::uuid as item_id,
            coicop_division,
            coicop_code
        from {{ ref('int_coicop_classified') }}
        order by item_id::uuid,
                 case when coicop_division <> 'UNCLASSIFIED' then 1 else 2 end,
                 coicop_confidence desc
    ) cs on cs.item_id = ci.item_id
    join {{ ref('fct_daily_prices') }} fdp on fdp.item_id = ci.item_id::uuid
    where fdp.store_slug in ('aeon', 'aeon3')
)
select * from classified_products
