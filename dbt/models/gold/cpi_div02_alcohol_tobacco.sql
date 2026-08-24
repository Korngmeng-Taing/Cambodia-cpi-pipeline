-- cpi_div02_alcohol_tobacco
-- Stable public alias for COICOP Division 02: Alcoholic beverages, tobacco and narcotics.
-- Kept as a dbt model (not a hand-written view in sql/views.sql) so dbt resolves the
-- dependency on div02_alcohol_tobacco and rebuilds both together instead of CASCADE-dropping it.
{{ config(
    materialized='view'
) }}

select * from {{ ref('div02_alcohol_tobacco') }}
