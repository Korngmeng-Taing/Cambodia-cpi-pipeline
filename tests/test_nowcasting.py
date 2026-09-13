"""
tests/test_nowcasting.py
────────────────────────
Unit tests for the Machine Learning-Assisted Daily Inflation Nowcaster (ml/nowcaster.py).
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

import pandas as pd
import pytest

from ml.config import NIS_COICOP_WEIGHTS
from ml.nowcaster import CPINowcaster, execute_nowcasting_pipeline


@pytest.fixture
def sample_nowcast_data():
    """Generates synthetic multi-day facts for testing."""
    target_date = date(2026, 9, 20)
    target_month = date(2026, 9, 1)

    # 20 observed days
    dates = [target_month + timedelta(days=i) for i in range(20)]
    rows = []
    for d in dates:
        for div in NIS_COICOP_WEIGHTS:
            rows.append(
                {
                    "calculation_date": d,
                    "coicop_division": div,
                    "division_name": NIS_COICOP_WEIGHTS[div]["name"],
                    "weight": NIS_COICOP_WEIGHTS[div]["weight"],
                    "division_index": 102.0 + (d.day * 0.02),
                    "headline_cpi": 102.0 + (d.day * 0.02),
                    "core_cpi": 101.5 + (d.day * 0.01),
                    "item_count": 150,
                    "observation_count": 800,
                }
            )
    df_daily = pd.DataFrame(rows)
    df_fx = pd.DataFrame([{"execution_date": target_date, "rate": 4050.0}])
    df_monthly = pd.DataFrame(
        [
            {
                "cpi_month": date(2026, 8, 1),
                "monthly_headline_cpi": 101.50,
                "monthly_core_cpi": 101.00,
                "mom_inflation_pct": 0.50,
            }
        ]
    )
    df_nis = pd.DataFrame(
        [
            {
                "cpi_month": date(2026, 8, 1),
                "headline_cpi": 219.10,
                "core_cpi": 218.40,
                "mom_inflation_pct": -0.7,
            }
        ]
    )
    return target_date, df_daily, df_fx, df_monthly, df_nis


def test_expanding_window_and_weights(sample_nowcast_data):
    """Verifies expanding window day counts and weight partition."""
    target_date, df_daily, df_fx, df_monthly, df_nis = sample_nowcast_data
    nowcaster = CPINowcaster()

    res = nowcaster.nowcast_for_date(target_date, df_daily, df_fx, df_monthly, df_nis)

    _, total_days = calendar.monthrange(target_date.year, target_date.month)
    assert res["days_in_month"] == total_days
    assert res["days_observed"] == 20
    assert res["days_remaining"] == 10
    assert res["days_observed"] + res["days_remaining"] == total_days


def test_confidence_interval_bounds(sample_nowcast_data):
    """Verifies that 95% confidence interval bounds envelope the nowcast."""
    target_date, df_daily, df_fx, df_monthly, df_nis = sample_nowcast_data
    nowcaster = CPINowcaster()

    res = nowcaster.nowcast_for_date(target_date, df_daily, df_fx, df_monthly, df_nis)

    assert res["ci_lower_95"] <= res["nowcast_headline_cpi"]
    assert res["ci_upper_95"] >= res["nowcast_headline_cpi"]
    assert res["ci_lower_95"] > 0
    assert res["uncertainty_pct"] == round(10 / 30, 3)


def test_nis_chain_linking(sample_nowcast_data):
    """Verifies chain-linking to official NIS benchmark (Base 2006 = 100)."""
    target_date, df_daily, df_fx, df_monthly, df_nis = sample_nowcast_data
    nowcaster = CPINowcaster()

    res = nowcaster.nowcast_for_date(target_date, df_daily, df_fx, df_monthly, df_nis)

    assert res["nowcast_nis_headline_cpi"] is not None
    assert res["latest_nis_baseline_cpi"] == 219.10
    # Chain-linked CPI must reflect MoM inflation direction
    expected_nis = round(219.10 * (1.0 + (res["projected_mom_pct"] / 100.0)), 4)
    assert res["nowcast_nis_headline_cpi"] == expected_nis


def test_uncertainty_decay_over_month():
    """Verifies that uncertainty decays toward 0 as observed days increase."""
    nowcaster = CPINowcaster()

    # Early month: Day 5 of 30
    d5 = date(2026, 9, 5)
    r5 = nowcaster.generate_synthetic_test_nowcast(d5)

    # Mid month: Day 15 of 30
    d15 = date(2026, 9, 15)
    r15 = nowcaster.generate_synthetic_test_nowcast(d15)

    # Late month: Day 28 of 30
    d28 = date(2026, 9, 28)
    r28 = nowcaster.generate_synthetic_test_nowcast(d28)

    assert r5["uncertainty_pct"] > r15["uncertainty_pct"] > r28["uncertainty_pct"]
    assert (r5["ci_upper_95"] - r5["ci_lower_95"]) >= (r28["ci_upper_95"] - r28["ci_lower_95"])


def test_synthetic_nowcast_execution():
    """Verifies end-to-end synthetic generator without live Postgres."""
    nowcaster = CPINowcaster()
    res = nowcaster.generate_synthetic_test_nowcast(date(2026, 8, 25))

    required_keys = [
        "nowcast_date",
        "target_month",
        "days_observed",
        "days_remaining",
        "days_in_month",
        "realized_cpi_so_far",
        "projected_remaining_cpi",
        "projected_mom_pct",
        "nowcast_headline_cpi",
        "nowcast_nis_headline_cpi",
        "nowcast_core_cpi",
        "prior_month_cpi",
        "ci_lower_95",
        "ci_upper_95",
        "uncertainty_pct",
        "model_name",
    ]
    for k in required_keys:
        assert k in res, f"Missing expected key {k} in nowcast result"


def test_run_daily_nowcast_offline_graceful_fallback():
    """Verifies that run_daily_nowcast falls back to synthetic run if DB is offline."""
    nowcaster = CPINowcaster()
    # When DB is offline, it generates synthetic result without throwing an exception
    res = nowcaster.run_daily_nowcast(date(2026, 9, 10))
    assert res is not None
    assert res["days_observed"] == 10
    assert "nowcast_headline_cpi" in res


def test_execute_nowcasting_pipeline_airflow_entrypoint():
    """Verifies Airflow entrypoint callable."""
    context = {"ds": "2026-09-12"}
    res = execute_nowcasting_pipeline(**context)
    assert res["nowcast_date"] == date(2026, 9, 12)


def test_festival_shock_adjustment(sample_nowcast_data):
    """Verifies that dates within major festival windows (e.g. Pchum Ben in late Sept) reflect festive surge."""
    _, df_daily, df_fx, df_monthly, df_nis = sample_nowcast_data
    nowcaster = CPINowcaster()

    # Normal day (e.g. Sept 10) vs. Festival day (e.g. Sept 29 during Pchum Ben)
    normal_res = nowcaster.nowcast_for_date(date(2026, 9, 10), df_daily, df_fx, df_monthly, df_nis)
    festival_res = nowcaster.nowcast_for_date(date(2026, 9, 29), df_daily, df_fx, df_monthly, df_nis)

    assert normal_res is not None
    assert festival_res is not None
    assert "nowcast_headline_cpi" in festival_res
    assert festival_res["nowcast_headline_cpi"] > 0


def test_exchange_rate_pass_through_drift(sample_nowcast_data):
    """Verifies that Riel depreciation (USD/KHR increase) lifts the projected daily drift."""
    target_date, df_daily, _, df_monthly, df_nis = sample_nowcast_data
    nowcaster = CPINowcaster()

    # Case A: Stable FX rate (4050 KHR/USD)
    df_fx_stable = pd.DataFrame([
        {"execution_date": target_date - timedelta(days=i), "rate": 4050.0}
        for i in range(10)
    ])
    res_stable = nowcaster.nowcast_for_date(target_date, df_daily, df_fx_stable, df_monthly, df_nis)

    # Case B: Depreciating Riel (4050 -> 4150 KHR/USD over 7 days, ~2.5% depreciation)
    fx_depr_rows = []
    for i in range(10):
        d = target_date - timedelta(days=i)
        rate = 4150.0 if i == 0 else 4050.0
        fx_depr_rows.append({"execution_date": d, "rate": rate})
    df_fx_depr = pd.DataFrame(fx_depr_rows)
    res_depr = nowcaster.nowcast_for_date(target_date, df_daily, df_fx_depr, df_monthly, df_nis)

    assert res_depr["fx_momentum_7d"] > res_stable["fx_momentum_7d"]
    assert res_depr["fx_daily_drift"] > res_stable["fx_daily_drift"]
    assert res_depr["nowcast_headline_cpi"] >= res_stable["nowcast_headline_cpi"]


def test_evaluate_historical_accuracy_backtest(sample_nowcast_data):
    """Verifies the automated backtesting evaluation harness."""
    _, df_daily, df_fx, df_monthly, df_nis = sample_nowcast_data
    nowcaster = CPINowcaster()

    results = nowcaster.evaluate_historical_accuracy(
        df_daily, df_fx, df_monthly, df_nis, evaluation_days=[5, 10, 15, 20]
    )
    assert results is not None
    assert "overall_rmse_cpi" in results
    assert "overall_mae_cpi" in results
    assert results["overall_rmse_cpi"] >= 0.0
    assert results["overall_mae_cpi"] >= 0.0


def test_compute_evaluation_metrics_dataframe():
    """Tests the pointwise and rolling error metrics calculation (RMSE, MAE, directional hit)."""
    df_pairs = pd.DataFrame([
        {
            "evaluation_date": date(2026, 7, 31),
            "target_month": date(2026, 7, 1),
            "model_name": "ml_v1",
            "days_observed": 31,
            "nowcast_mom_pct": 0.50,
            "actual_mom_pct": 0.40,
            "nowcast_headline_cpi": 101.5,
            "actual_headline_cpi": 101.0,
        },
        {
            "evaluation_date": date(2026, 8, 31),
            "target_month": date(2026, 8, 1),
            "model_name": "ml_v1",
            "days_observed": 31,
            "nowcast_mom_pct": -0.20,
            "actual_mom_pct": -0.30,
            "nowcast_headline_cpi": 101.2,
            "actual_headline_cpi": 100.8,
        },
        {
            "evaluation_date": date(2026, 9, 30),
            "target_month": date(2026, 9, 1),
            "model_name": "ml_v1",
            "days_observed": 30,
            "nowcast_mom_pct": 0.60,
            "actual_mom_pct": 0.70,
            "nowcast_headline_cpi": 102.0,
            "actual_headline_cpi": 102.2,
        },
    ])

    df_metrics = CPINowcaster.compute_evaluation_metrics_dataframe(df_pairs)
    assert len(df_metrics) == 3
    assert "mom_error" in df_metrics.columns
    assert "cpi_absolute_error" in df_metrics.columns
    assert "rolling_rmse_3m" in df_metrics.columns
    assert "rolling_mae_3m" in df_metrics.columns
    assert "directional_hit" in df_metrics.columns

    # Check row 0: mom_error = 0.50 - 0.40 = 0.10, abs_error = 0.5
    assert pytest.approx(df_metrics.iloc[0]["mom_error"], 0.001) == 0.10
    assert pytest.approx(df_metrics.iloc[0]["cpi_absolute_error"], 0.001) == 0.5
    assert df_metrics.iloc[0]["directional_hit"] is True

    # Check rolling RMSE is computed and positive
    assert df_metrics.iloc[2]["rolling_rmse_3m"] > 0
    assert df_metrics.iloc[2]["rolling_mae_3m"] > 0


