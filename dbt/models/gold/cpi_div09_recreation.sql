-- cpi_div09_recreation
-- Stable public alias for COICOP Division 09: Recreation and culture.
-- Kept as a dbt model (not a hand-written view in sql/views.sql) so dbt resolves the
-- dependency on div09_recreation and rebuilds both together instead of CASCADE-dropping it.
{{ config(
    materialized='view'
) }}

select * from {{ ref('div09_recreation') }}
