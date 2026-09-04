-- migrations/018_cpi_ml_forecaster.sql
-- =============================================================================
-- CAMBODIA DAILY CPI — MACHINE LEARNING MULTI-HORIZON FORECASTING SCHEMA
-- LightGBM Regressors predicting 7-day, 14-day, and 30-day forward inflation.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS gold;

-- 1. Table to store forward machine learning daily inflation projections
CREATE TABLE IF NOT EXISTS gold.fct_cpi_forecast (
    forecast_execution_date DATE NOT NULL,
    target_date DATE NOT NULL,
    horizon_days INT NOT NULL,
    current_headline_cpi NUMERIC(10, 4) NOT NULL,
    predicted_inflation_pct NUMERIC(8, 4) NOT NULL,
    projected_headline_cpi NUMERIC(10, 4) NOT NULL,
    model_name VARCHAR(50) NOT NULL,
    model_rmse NUMERIC(8, 4),
    model_mae NUMERIC(8, 4),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (forecast_execution_date, target_date, horizon_days, model_name)
);

CREATE INDEX IF NOT EXISTS idx_fct_cpi_forecast_date ON gold.fct_cpi_forecast(forecast_execution_date);
CREATE INDEX IF NOT EXISTS idx_fct_cpi_forecast_target ON gold.fct_cpi_forecast(target_date);
CREATE INDEX IF NOT EXISTS idx_fct_cpi_forecast_horizon ON gold.fct_cpi_forecast(horizon_days);

-- 2. Continuous Daily CPI Actuals & Forward ML Inflation Forecast Chart View
CREATE OR REPLACE VIEW gold.v_cpi_forecast_chart AS
WITH actual_daily AS (
    SELECT
        calculation_date AS time_point,
        MAX(headline_cpi) AS actual_cpi,
        NULL::NUMERIC(10, 4) AS forecast_cpi,
        NULL::NUMERIC(8, 4) AS predicted_inflation_pct,
        'Actual Historical' AS series_type,
        0 AS horizon_days
    FROM gold.fct_cpi_daily
    GROUP BY calculation_date
),
latest_forecasts AS (
    SELECT
        target_date AS time_point,
        NULL::NUMERIC(10, 4) AS actual_cpi,
        projected_headline_cpi AS forecast_cpi,
        predicted_inflation_pct,
        'ML Forward Forecast' AS series_type,
        horizon_days
    FROM gold.fct_cpi_forecast
    WHERE forecast_execution_date = (SELECT MAX(forecast_execution_date) FROM gold.fct_cpi_forecast)
)
SELECT * FROM actual_daily
UNION ALL
SELECT * FROM latest_forecasts
ORDER BY time_point ASC, series_type DESC;

GRANT SELECT ON ALL TABLES IN SCHEMA gold TO cpi_user;
