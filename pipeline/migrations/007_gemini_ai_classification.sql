-- =============================================================================
-- 007_gemini_ai_classification.sql
-- Silver-layer AI COICOP classification support (Prompt 5).
--
-- - Creates silver.dim_coicop_ai_cache: memoizes one Gemini result per product
--   name so a name that has already been classified never triggers an API call
--   again (saves API costs across daily runs).
-- - Adds the COICOP output columns to staging.stg_item_mapping so the Gemini
--   classifier (pipeline/gemini_coicop_classifier.py) can persist
--   coicop_code / classification_method / confidence_score per mapped row.
--
-- Idempotent: safe to re-run. Applied to the running DB with:
--   psql -U cpi_user -d cpi_db -f pipeline/migrations/007_gemini_ai_classification.sql
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS silver;

-- -----------------------------------------------------------------------------
-- 1. Gemini result cache (memoization keyed on product name)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.dim_coicop_ai_cache (
    product_name TEXT PRIMARY KEY,
    coicop_code VARCHAR(16) NOT NULL,
    confidence_score NUMERIC(5, 4),
    reasoning TEXT,
    model_version VARCHAR(64),
    classified_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- 2. COICOP output columns on the raw-item -> canonical-item mapping
-- -----------------------------------------------------------------------------
ALTER TABLE staging.stg_item_mapping
    ADD COLUMN IF NOT EXISTS coicop_code VARCHAR(16),
    ADD COLUMN IF NOT EXISTS classification_method VARCHAR(32),
    ADD COLUMN IF NOT EXISTS confidence_score NUMERIC(5, 4);

CREATE INDEX IF NOT EXISTS idx_stg_mapping_coicop
    ON staging.stg_item_mapping(coicop_code);