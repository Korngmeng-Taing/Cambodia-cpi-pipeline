"""
tests/test_cpi_forecaster.py
────────────────────────────
Unit and integration tests for the Daily ML Inflation Forecaster.
"""

from datetime import date, timedelta
import numpy as np
import pandas as pd
import pytest

from ml.config import FORECAST_HORIZONS, NIS_COICOP_WEIGHTS
from ml.features import extract_daily_forecasting_features
from ml.forecaster import DailyCPIForecaster, execute_forecasting_pipeline


def test_daily_feature_extraction():
    """Verify that feature engineering extracts lags, moving averages, and targets properly."""
    dates = [date(2026, 8, 1) + timedelta(days=i) for i in range(40)]
    mock_rows = []
    base_cpi = 100.0

    for i, d in enumerate(dates):
        cpi = base_cpi + (0.05 * i)
        for div in ["01", "04", "07"]:
            mock_rows.append({
                "calculation_date": d,
                "coicop_division": div,
                "division_name": NIS_COICOP_WEIGHTS[div]["name"],
                "weight": NIS_COICOP_WEIGHTS[div]["weight"],
                "division_index": cpi + (0.02 if div == "01" else -0.01),
                "headline_cpi": cpi,
                "core_cpi": cpi - 0.1,
            })

    df_daily = pd.DataFrame(mock_rows)
    df_features = extract_daily_forecasting_features(df_daily, forward_days=7)

    assert not df_features.empty
    assert len(df_features) == 40
    assert "headline_cpi" in df_features.columns
    assert "dod_pct" in df_features.columns
    assert "ma_7" in df_features.columns
    assert "ma_14" in df_features.columns
    assert "ma_30" in df_features.columns
    assert "momentum_7_30" in df_features.columns
    assert "volatility_7d" in df_features.columns
    assert "food_momentum_7d" in df_features.columns
    assert "transport_momentum_7d" in df_features.columns
    assert "is_weekend" in df_features.columns
    assert "target" in df_features.columns

    # Check target calculation: target should be valid up to row index 40 - 7 = 33
    valid_targets = df_features["target"].dropna()
    assert len(valid_targets) == 33


def test_forecaster_synthetic_execution():
    """Verify that DailyCPIForecaster runs end-to-end on synthetic data and outputs all horizons."""
    forecaster = DailyCPIForecaster()
    target_date = date(2026, 8, 20)
    forecasts = forecaster.generate_synthetic_test_forecast(target_date)

    assert len(forecasts) == len(FORECAST_HORIZONS)
    horizon_days_set = {f["horizon_days"] for f in forecasts}
    assert horizon_days_set == {7, 14, 30}

    for f in forecasts:
        assert f["forecast_execution_date"] == target_date
        assert f["target_date"] == target_date + timedelta(days=f["horizon_days"])
        assert f["current_headline_cpi"] > 0
        assert "predicted_inflation_pct" in f
        assert "projected_headline_cpi" in f
        assert f["projected_headline_cpi"] > 0

        # Verify mathematical consistency of projected CPI level
        expected_cpi = round(
            float(f["current_headline_cpi"] * (1.0 + (f["predicted_inflation_pct"] / 100.0))), 4
        )
        assert f["projected_headline_cpi"] == expected_cpi


def test_small_sample_fallback():
    """Verify graceful handling when fewer than 15 historical days exist."""
    forecaster = DailyCPIForecaster()
    dates = [date(2026, 8, 1) + timedelta(days=i) for i in range(8)]
    mock_rows = []
    for i, d in enumerate(dates):
        mock_rows.append({
            "calculation_date": d,
            "headline_cpi": 100.0 + i * 0.05,
            "core_cpi": 100.0,
            "food_index": 100.0 + i * 0.05,
            "transport_index": 100.0,
        })
    df_small = pd.DataFrame(mock_rows)

    res = forecaster.train_and_forecast_horizon(df_small, horizon_days=7)
    assert res["horizon_days"] == 7
    assert res["current_headline_cpi"] == 100.35
    assert "predicted_inflation_pct" in res
    assert res["projected_headline_cpi"] > 0
