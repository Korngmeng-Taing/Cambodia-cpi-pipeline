-- cpi_div12_misc
-- Stable public alias for COICOP Division 12: Miscellaneous goods and services.
-- Kept as a dbt model (not a hand-written view in sql/views.sql) so dbt resolves the
-- dependency on div12_misc and rebuilds both together instead of CASCADE-dropping it.
{{ config(
    materialized='view'
) }}

select * from {{ ref('div12_misc') }}
