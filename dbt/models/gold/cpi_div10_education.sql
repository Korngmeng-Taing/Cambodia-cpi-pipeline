-- cpi_div10_education
-- Stable public alias for COICOP Division 10: Education.
-- Kept as a dbt model (not a hand-written view in sql/views.sql) so dbt resolves the
-- dependency on div10_education and rebuilds both together instead of CASCADE-dropping it.
{{ config(
    materialized='view'
) }}

select * from {{ ref('div10_education') }}
