-- cpi_div07_transport
-- Stable public alias for COICOP Division 07: Transport.
-- Kept as a dbt model (not a hand-written view in sql/views.sql) so dbt resolves the
-- dependency on div07_transport and rebuilds both together instead of CASCADE-dropping it.
{{ config(
    materialized='view'
) }}

select * from {{ ref('div07_transport') }}
