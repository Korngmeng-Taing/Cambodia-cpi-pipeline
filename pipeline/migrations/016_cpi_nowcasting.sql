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
    projected_mom_pct NUMERIC(8, 4) NOT NULL,       -- TARGET: Estimated MoM inflation rate (%)
    nowcast_headline_cpi NUMERIC(10, 4) NOT NULL,   -- Pipeline-native base Headline CPI estimate
    nowcast_nis_headline_cpi NUMERIC(10, 4),        -- Chain-linked official NIS Headline CPI estimate (Base 2006)
    nowcast_core_cpi NUMERIC(10, 4),                -- Combined full-month Core CPI estimate
    prior_month_cpi NUMERIC(10, 4),                 -- Previous month's final CPI
    ci_lower_95 NUMERIC(10, 4),                     -- 95% Confidence Interval lower bound
    ci_upper_95 NUMERIC(10, 4),                     -- 95% Confidence Interval upper bound
    uncertainty_pct NUMERIC(6, 3),                  -- Dynamic uncertainty ratio (days_remaining / days_in_month)
    model_name VARCHAR(50) DEFAULT 'hybrid_adl_gbrt_v1',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (nowcast_date, target_month, model_name)
);

CREATE INDEX IF NOT EXISTS idx_fct_cpi_nowcast_target_month ON gold.fct_cpi_nowcast(target_month);
CREATE INDEX IF NOT EXISTS idx_fct_cpi_nowcast_date ON gold.fct_cpi_nowcast(nowcast_date);

-- Seed official NIS Phnom Penh CPI releases (Oct-Dec 2006 = 100) from Table 2
INSERT INTO gold.dim_nis_official_cpi (cpi_month, headline_cpi, mom_inflation_pct, yoy_inflation_pct, release_date, source_notes)
VALUES
    ('2025-07-01', 207.7, NULL, NULL, '2025-08-25', 'NIS Phnom Penh Table 2 (Jul-25)'),
    ('2026-06-01', 220.8, NULL, NULL, '2026-07-25', 'NIS Phnom Penh Table 2 (Jun-26)'),
    ('2026-07-01', 219.1, -0.7, 5.5, '2026-08-25', 'NIS Phnom Penh Table 2 (Jul-26)')
ON CONFLICT (cpi_month) DO UPDATE
SET headline_cpi = EXCLUDED.headline_cpi,
    mom_inflation_pct = EXCLUDED.mom_inflation_pct,
    yoy_inflation_pct = EXCLUDED.yoy_inflation_pct,
    release_date = EXCLUDED.release_date,
    source_notes = EXCLUDED.source_notes;

-- 4. View for Out-of-Sample Nowcasting Evaluation & Tracking vs. Official NIS Benchmarks
CREATE OR REPLACE VIEW gold.v_nowcast_evaluation AS
SELECT 
    n.nowcast_date,
    n.target_month,
    n.days_observed,
    n.days_remaining,
    n.projected_mom_pct AS nowcasted_mom_pct,
    o.mom_inflation_pct AS actual_nis_mom_pct,
    ROUND(n.projected_mom_pct - o.mom_inflation_pct, 4) AS mom_forecast_error,
    n.nowcast_nis_headline_cpi AS nowcasted_nis_cpi,
    o.headline_cpi AS actual_nis_cpi,
    ROUND(n.nowcast_nis_headline_cpi - o.headline_cpi, 4) AS cpi_forecast_error,
    n.ci_lower_95,
    n.ci_upper_95,
    CASE 
        WHEN o.headline_cpi BETWEEN n.ci_lower_95 AND n.ci_upper_95 THEN TRUE 
        ELSE FALSE 
    END AS is_within_95_ci,
    n.model_name
FROM gold.fct_cpi_nowcast n
JOIN gold.dim_nis_official_cpi o ON n.target_month = o.cpi_month
ORDER BY n.nowcast_date DESC;
