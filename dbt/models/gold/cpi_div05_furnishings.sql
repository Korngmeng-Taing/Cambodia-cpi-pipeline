-- cpi_div05_furnishings
-- Stable public alias for COICOP Division 05: Furnishings, household equipment and routine maintenance.
-- Kept as a dbt model (not a hand-written view in sql/views.sql) so dbt resolves the
-- dependency on div05_furnishings and rebuilds both together instead of CASCADE-dropping it.
{{ config(
    materialized='view'
) }}

select * from {{ ref('div05_furnishings') }}
