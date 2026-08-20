-- stg_bronze_external
-- Bronze observations as read from the parquet snapshots archived in MinIO
-- (s3://cpi-bronze/parquet/...). Postgres bronze.raw_prices is the relational
-- mirror of those snapshots, so this model exposes the same contract.
{{ config(materialized='view') }}

select
    raw_price_id,
    store_id,
    item_description_raw,
    price,
    currency,
    scraped_at,
    scraped_at::date as scrape_date,
    source_url,
    source_name,
    batch_id,
    raw_payload,
    created_at
from {{ source('bronze_external', 'raw_prices') }}
