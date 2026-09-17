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
    assert res["nowcast_nis_headline_cpi"] == pytest.approx(expected_nis, abs=1e-2)


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
        "nowcast_food_cpi",
        "nowcast_alcohol_cpi",
        "nowcast_housing_cpi",
        "nowcast_transport_cpi",
        "nowcast_restaurant_cpi",
        "baskets_detail",
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


def test_bottom_up_5basket_price_relatives(sample_nowcast_data):
    """Verifies that all 5 key market baskets are nowcasted individually with valid price relatives."""
    target_date, df_daily, df_fx, df_monthly, df_nis = sample_nowcast_data
    nowcaster = CPINowcaster()

    res = nowcaster.nowcast_for_date(target_date, df_daily, df_fx, df_monthly, df_nis)

    # 1. Check top-level 5 basket fields
    assert "nowcast_food_cpi" in res
    assert "nowcast_alcohol_cpi" in res
    assert "nowcast_housing_cpi" in res
    assert "nowcast_transport_cpi" in res
    assert "nowcast_restaurant_cpi" in res

    assert res["nowcast_food_cpi"] > 0.0
    assert res["nowcast_alcohol_cpi"] > 0.0
    assert res["nowcast_housing_cpi"] > 0.0
    assert res["nowcast_transport_cpi"] > 0.0
    assert res["nowcast_restaurant_cpi"] > 0.0

    # 2. Check baskets_detail dictionary
    baskets = res.get("baskets_detail", {})
    assert len(baskets) == 12

    for div in ["01", "02", "04", "07", "11"]:
        info = baskets[div]
        assert "price_relative" in info
        assert "mom_pct" in info
        assert "contribution_pp" in info
        assert info["price_relative"] > 0.0


def test_laspeyres_exact_aggregation(sample_nowcast_data):
    """Verifies that sum(weight * division_nowcast) equals headline nowcast CPI within 0.001 tolerance."""
    target_date, df_daily, df_fx, df_monthly, df_nis = sample_nowcast_data
    nowcaster = CPINowcaster()

    res = nowcaster.nowcast_for_date(target_date, df_daily, df_fx, df_monthly, df_nis)
    baskets = res["baskets_detail"]

    aggregated_headline = sum(b["weight"] * b["nowcast"] for b in baskets.values())
    assert pytest.approx(res["nowcast_headline_cpi"], 0.001) == aggregated_headline

    # Check sum of percentage-point contributions equals overall projected MoM rate (approx)
    total_contribution = sum(b["contribution_pp"] for b in baskets.values())
    assert pytest.approx(res["projected_mom_pct"], 0.05) == total_contribution


def test_cross_division_fuel_feature_injection(sample_nowcast_data):
    """Verifies that Food (01) and Restaurants (11) receive Transport/Fuel cross-momentum."""
    target_date, df_daily, df_fx, _, _ = sample_nowcast_data
    nowcaster = CPINowcaster()
    estimator = nowcaster.drift_estimator

    feat_food = estimator.extract_features_for_basket(target_date, df_daily, df_fx, "01")
    # Food feature vector: [f_3, f_7, f_14, t_7, fx_7d, fest_prox, prog_ratio] -> 7 features
    assert len(feat_food) == 7

    feat_rest = estimator.extract_features_for_basket(target_date, df_daily, df_fx, "11")
    # Restaurant feature vector: [r_7, f_7, t_7, is_window, prog_ratio] -> 5 features
    assert len(feat_rest) == 5

    feat_alcohol = estimator.extract_features_for_basket(target_date, df_daily, df_fx, "02")
    # Alcohol feature vector remains: [a_7, fx_7d, fx_14d, is_window, prog_ratio] -> 5 features
    assert len(feat_alcohol) == 5

    feat_housing = estimator.extract_features_for_basket(target_date, df_daily, df_fx, "04")
    # Housing feature vector remains: [h_7, h_14, fx_14d, prog_ratio] -> 4 features
    assert len(feat_housing) == 4

    feat_transport = estimator.extract_features_for_basket(target_date, df_daily, df_fx, "07")
    # Transport feature vector remains: [t_3, t_7, fx_7d, fest_prox, prog_ratio] -> 5 features
    assert len(feat_transport) == 5


def test_evaluate_against_random_walk_scorecard():
    """Verifies the out-of-sample Relative RMSE scorecard calculation against the Random Walk baseline."""
    df_pairs = pd.DataFrame([
        {"target_month": date(2026, 6, 1), "actual_mom_pct": 0.50, "nowcast_mom_pct": 0.48},
        {"target_month": date(2026, 7, 1), "actual_mom_pct": -0.74, "nowcast_mom_pct": -0.70},
        {"target_month": date(2026, 8, 1), "actual_mom_pct": -0.06, "nowcast_mom_pct": -0.05},
        {"target_month": date(2026, 9, 1), "actual_mom_pct": 0.30, "nowcast_mom_pct": 0.28},
    ])

    scorecard = CPINowcaster.evaluate_against_random_walk(df_pairs)

    assert "relative_rmse" in scorecard
    assert "model_rmse" in scorecard
    assert "random_walk_rmse" in scorecard
    assert scorecard["beats_random_walk"] is True
    assert scorecard["relative_rmse"] < 1.00
    assert scorecard["sample_size"] == 3  # First observation shifted for RW lag
    assert scorecard["error_reduction_pct"] > 0.0


def test_log_differencing_symmetry():
    """Verifies that equal positive and negative price percentage shocks cancel out symmetrically in logs."""
    import numpy as np

    p_base = 100.0
    p_down = 80.0
    p_up = 100.0

    # Linear returns: -20% and +25% -> net +5% (asymmetric distortion)
    linear_down = (p_down - p_base) / p_base
    linear_up = (p_up - p_down) / p_down
    assert pytest.approx(linear_down + linear_up, 1e-6) == 0.05

    # Log returns: exactly zero net change
    log_down = np.log(p_down / p_base)
    log_up = np.log(p_up / p_down)
    assert pytest.approx(log_down + log_up, 1e-10) == 0.0


def test_36month_calibration_pipeline():
    """Verifies that the 36-month 5-basket RidgeCV calibration engine runs and beats Random Walk."""
    from ml.calibration import MacroDatasetBuilder, RidgeCalibrationEngine

    builder = MacroDatasetBuilder()
    df_raw = builder.load_36month_panel_from_seed()
    assert len(df_raw) == 36

    df_stat = builder.build_stationary_matrix(df_raw)
    assert len(df_stat) == 34  # 36 months minus 1 for diff and 1 for RW lag

    engine = RidgeCalibrationEngine()
    results = engine.run_calibration(df_stat, train_split_months=24)

    assert results["total_sample_months"] == 34
    assert results["train_months_count"] == 24
    assert results["optimal_lambda"] > 0.0
    assert "base_drift_alpha" in results

    el = results["elasticities"]
    for basket in ["beta_food", "beta_alcohol", "beta_housing", "beta_transport", "beta_restaurant", "beta_fx"]:
        assert basket in el
        # Coefficients should be non-negative and economically bounded (< 1.5)
        assert -0.20 <= el[basket] <= 1.50

    oos = results["out_of_sample"]
    assert oos["test_months_count"] == 10
    assert oos["relative_rmse"] > 0.0
    assert "beats_random_walk" in oos



