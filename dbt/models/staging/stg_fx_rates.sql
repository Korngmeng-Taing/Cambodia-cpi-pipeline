-- stg_fx_rates
-- Staging view over the MEF USD/KHR official daily exchange rate.
{{ config(materialized='view') }}

select
    execution_date,
    rate,
    source,
    is_stale,
    raw_payload,
    fetched_at
from {{ source('staging', 'exchange_rates') }}
