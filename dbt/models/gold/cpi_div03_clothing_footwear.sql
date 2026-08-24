-- cpi_div03_clothing_footwear
-- Stable public alias for COICOP Division 03: Clothing and footwear.
-- Kept as a dbt model (not a hand-written view in sql/views.sql) so dbt resolves the
-- dependency on div03_clothing_footwear and rebuilds both together instead of CASCADE-dropping it.
{{ config(
    materialized='view'
) }}

select * from {{ ref('div03_clothing_footwear') }}
