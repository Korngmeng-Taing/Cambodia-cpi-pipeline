-- =============================================================================
-- 008_clean_silver_layer.sql
-- Silver Layer Cleanup & Optimization
-- 
-- 1. Drops legacy / deprecated tables that clutter Metabase
-- 2. Ensures clean conformed Star Schema in the silver schema
-- 3. Idempotent: safe to run multiple times
-- =============================================================================

-- Drop legacy tables from previous lakehouse / manual iterations if they exist
DROP TABLE IF EXISTS silver.daily_prices CASCADE;
DROP TABLE IF EXISTS silver.products CASCADE;
DROP TABLE IF EXISTS silver.store_products CASCADE;
DROP TABLE IF EXISTS silver.dq_silver CASCADE;
DROP TABLE IF EXISTS silver.item_master CASCADE;
DROP TABLE IF EXISTS silver.items_normalized CASCADE;

-- Drop intermediate views from silver schema (they are now generated in staging schema)
DROP VIEW IF EXISTS silver.int_prices_cleaned CASCADE;
DROP VIEW IF EXISTS silver.int_coicop_classified CASCADE;

-- Ensure indexes on operational tables
CREATE INDEX IF NOT EXISTS idx_item_match_log_item_id ON silver.item_match_log(item_id);
CREATE INDEX IF NOT EXISTS idx_canonical_items_name ON silver.canonical_items(canonical_name);
