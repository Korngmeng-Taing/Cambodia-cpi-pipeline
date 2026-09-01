-- migrations/016_cpi_nowcasting.sql
-- =============================================================================
-- CAMBODIA DAILY CPI — MONTHLY INFLATION NOWCASTING SCHEMA
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS gold;

-- 1. Table to store historical official NIS monthly CPI records for ground-truth benchmarking
CREATE TABLE IF NOT EXISTS gold.dim_nis_official_cpi (
    cpi_month DATE NOT NULL PRIMARY KEY,            -- First day of the month (e.g. 2026-08-01)
    headline_cpi NUMERIC(10, 4) NOT NULL,           -- Official NIS Headline CPI
    core_cpi NUMERIC(10, 4),                        -- Official NIS Core CPI
    mom_inflation_pct NUMERIC(8, 4),                -- Month-over-Month inflation rate (%)
    yoy_inflation_pct NUMERIC(8, 4),                -- Year-over-Year inflation rate (%)
    release_date DATE,                              -- Date published by NIS
    source_notes TEXT DEFAULT 'NIS Cambodia Official CPI Release',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Table to store monthly macroeconomic signals (Imports, M2 Money Supply, Credit)
CREATE TABLE IF NOT EXISTS staging.macro_indicators (
    indicator_month DATE NOT NULL,                  -- First day of month (e.g. 2026-08-01)
    indicator_name VARCHAR(100) NOT NULL,           -- e.g. 'imports_usd_million', 'm2_money_supply_khr_trillion', 'private_credit_growth_pct'
    indicator_value NUMERIC(16, 4) NOT NULL,        -- Value
    source VARCHAR(100) DEFAULT 'NBC / GDCE',       -- National Bank of Cambodia / Customs
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (indicator_month, indicator_name)
);

-- 3. Table to store daily generated monthly inflation nowcasts
CREATE TABLE IF NOT EXISTS gold.fct_cpi_nowcast (
    nowcast_date DATE NOT NULL,                     -- Date nowcast was run (e.g. 2026-08-25)
    target_month DATE NOT NULL,                     -- Month being forecasted (e.g. 2026-08-01)
    days_observed INTEGER NOT NULL,                 -- Scraped days realized (e.g. 25)
    days_remaining INTEGER NOT NULL,                -- Days forecasted to end of month (e.g. 6)
    days_in_month INTEGER NOT NULL,                 -- Total days in month (e.g. 31)
    realized_cpi_so_far NUMERIC(10, 4),             -- Mean CPI of observed days
    projected_remaining_cpi NUMERIC(10, 4),         -- ML predicted mean CPI of remaining days
    nowcast_headline_cpi NUMERIC(10, 4) NOT NULL,   -- Combined full-month Headline CPI estimate
    nowcast_core_cpi NUMERIC(10, 4),                -- Combined full-month Core CPI estimate
    prior_month_cpi NUMERIC(10, 4),                 -- Previous month's final CPI
    projected_mom_pct NUMERIC(8, 4),                -- Estimated MoM inflation rate (%)
    projected_yoy_pct NUMERIC(8, 4),                -- Estimated YoY inflation rate (%)
    ci_lower_95 NUMERIC(10, 4),                     -- 95% Confidence Interval lower bound
    ci_upper_95 NUMERIC(10, 4),                     -- 95% Confidence Interval upper bound
    uncertainty_pct NUMERIC(6, 3),                  -- Dynamic uncertainty ratio (days_remaining / days_in_month)
    model_name VARCHAR(50) DEFAULT 'two_stage_hybrid_v1',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (nowcast_date, target_month, model_name)
);

CREATE INDEX IF NOT EXISTS idx_fct_cpi_nowcast_target_month ON gold.fct_cpi_nowcast(target_month);
