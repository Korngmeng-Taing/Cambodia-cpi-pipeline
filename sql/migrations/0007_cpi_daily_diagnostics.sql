-- Migration 0007: Operational Diagnostics & Stability Telemetry in gold.fct_cpi_daily
-- Adds coverage_weight and imputation_rate to track sample representation and imputation share.

ALTER TABLE gold.fct_cpi_daily 
ADD COLUMN IF NOT EXISTS coverage_weight NUMERIC(8, 4);

ALTER TABLE gold.fct_cpi_daily 
ADD COLUMN IF NOT EXISTS imputation_rate NUMERIC(8, 4);
