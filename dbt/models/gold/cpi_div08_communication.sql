-- cpi_div08_communication
-- Stable public alias for COICOP Division 08: Communication.
-- Kept as a dbt model (not a hand-written view in sql/views.sql) so dbt resolves the
-- dependency on div08_communication and rebuilds both together instead of CASCADE-dropping it.
{{ config(
    materialized='view'
) }}

select * from {{ ref('div08_communication') }}
