-- sql/migrations/0005_drop_unpartitioned_backups.sql
-- ─────────────────────────────────────────────
-- Drop obsolete unpartitioned migration backups to reclaim 2.18 GB of active storage.
-- All data is partitioned by month (raw_prices_YYYY_MM, clean_store_prices_YYYY_MM)
-- and archived into compressed Apache Parquet in data/cold_storage/.

DROP TABLE IF EXISTS bronze.raw_prices_unpartitioned_backup CASCADE;
DROP TABLE IF EXISTS silver.clean_store_prices_unpartitioned_backup CASCADE;
