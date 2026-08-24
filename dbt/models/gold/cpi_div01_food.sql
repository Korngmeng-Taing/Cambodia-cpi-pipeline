-- cpi_div01_food
-- Stable public alias for COICOP Division 01: Food and non-alcoholic beverages.
-- Kept as a dbt model (not a hand-written view in sql/views.sql) so dbt resolves the
-- dependency on div01_food and rebuilds both together instead of CASCADE-dropping it.
{{ config(
    materialized='view'
) }}

select * from {{ ref('div01_food') }}
