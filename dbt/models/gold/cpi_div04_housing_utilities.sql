-- cpi_div04_housing_utilities
-- Stable public alias for COICOP Division 04: Housing, water, electricity, gas and other fuels.
-- Kept as a dbt model (not a hand-written view in sql/views.sql) so dbt resolves the
-- dependency on div04_housing_utilities and rebuilds both together instead of CASCADE-dropping it.
{{ config(
    materialized='view'
) }}

select * from {{ ref('div04_housing_utilities') }}
