-- cpi_div11_restaurants_hotels
-- Stable public alias for COICOP Division 11: Restaurants and hotels.
-- Kept as a dbt model (not a hand-written view in sql/views.sql) so dbt resolves the
-- dependency on div11_restaurants_hotels and rebuilds both together instead of CASCADE-dropping it.
{{ config(
    materialized='view'
) }}

select * from {{ ref('div11_restaurants_hotels') }}
