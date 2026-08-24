-- cpi_div06_health
-- Stable public alias for COICOP Division 06: Health.
-- Kept as a dbt model (not a hand-written view in sql/views.sql) so dbt resolves the
-- dependency on div06_health and rebuilds both together instead of CASCADE-dropping it.
{{ config(
    materialized='view'
) }}

select * from {{ ref('div06_health') }}
