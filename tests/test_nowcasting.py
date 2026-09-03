"""
tests/test_nowcasting.py
────────────────────────
Unit and integration tests for the Inflation & CPI Nowcasting Engine.
"""

from datetime import date, timedelta
import pandas as pd
import pytest

from ml.config import CAMBODIA_ANNUAL_HOLIDAYS, NIS_COICOP_WEIGHTS
from ml.features import extract_nowcasting_features, get_holiday_features
from ml.nowcaster import CPINowcaster, execute_nowcasting_pipeline


def test_holiday_features():
    # Test Khmer New Year window (April 14)
    kny_date = date(2026, 4, 14)
    res_kny = get_holiday_features(kny_date)
    assert res_kny["is_holiday_window"] == 1
    assert res_kny["is_khmer_new_year"] == 1

    # Test normal date with no holiday (August 18)
    normal_date = date(2026, 8, 18)
    res_norm = get_holiday_features(normal_date)
    assert res_norm["is_holiday_window"] == 0
    assert res_norm["is_khmer_new_year"] == 0


def test_feature_extraction_empty_fallback():
    target_date = date(2026, 8, 15)
    empty_daily = pd.DataFrame()
    features = extract_nowcasting_features(target_date, empty_daily)

    assert features["target_date"] == target_date
    assert features["target_month"] == date(2026, 8, 1)
    assert features["days_observed"] == 15
    assert features["days_remaining"] == 16
    assert features["days_in_month"] == 31
    assert features["realized_headline_cpi"] == 100.0


def test_nowcaster_synthetic_execution():
    nowcaster = CPINowcaster()
    target_date = date(2026, 8, 20)
    res = nowcaster.generate_synthetic_test_nowcast(target_date)

    assert res["nowcast_date"] == target_date
    assert res["target_month"] == date(2026, 8, 1)
    assert res["days_observed"] == 20
    assert res["days_remaining"] == 11
    assert res["days_in_month"] == 31
    assert res["nowcast_headline_cpi"] > 0
    assert res["nowcast_core_cpi"] > 0
    assert "projected_mom_pct" in res
    assert "projected_yoy_pct" not in res

    # Check dual-index chain linking: NIS baseline should be linked to official base (192.50)
    assert "nowcast_nis_headline_cpi" in res
    assert res["latest_nis_baseline_cpi"] == 192.50
    expected_nis = round(192.50 * (1.0 + (res["projected_mom_pct"] / 100.0)), 4)
    assert res["nowcast_nis_headline_cpi"] == expected_nis

    # Check 95% Confidence Interval structure (ci_lower < cpi < ci_upper)
    assert res["ci_lower_95"] <= res["nowcast_headline_cpi"] <= res["ci_upper_95"]


def test_chain_linking_scale_invariance():
    """Verify that different official baselines correctly apply the same predicted inflation rate."""
    nowcaster = CPINowcaster()
    target_date = date(2026, 8, 20)
    
    # Test with custom official baselines (e.g. 189.50 vs 201.20)
    mock_daily = pd.DataFrame([
        {"calculation_date": date(2026, 8, 1), "coicop_division": "01", "division_name": "Food", "weight": 0.448, "division_index": 101.0, "headline_cpi": 101.0, "core_cpi": 101.0}
    ])
    df_nis_189 = pd.DataFrame([{"cpi_month": date(2026, 7, 1), "headline_cpi": 189.50, "core_cpi": 189.0, "mom_inflation_pct": 0.10}])
    df_nis_201 = pd.DataFrame([{"cpi_month": date(2026, 7, 1), "headline_cpi": 201.20, "core_cpi": 200.0, "mom_inflation_pct": 0.10}])

    res_189 = nowcaster.nowcast_for_date(target_date, mock_daily, df_nis=df_nis_189)
    res_201 = nowcaster.nowcast_for_date(target_date, mock_daily, df_nis=df_nis_201)

    # Both must predict identical MoM inflation rate regardless of base level
    assert res_189["projected_mom_pct"] == res_201["projected_mom_pct"]
    # Chain-linked values must scale exactly proportionally
    assert res_189["nowcast_nis_headline_cpi"] == round(189.50 * (1.0 + (res_189["projected_mom_pct"] / 100.0)), 4)
    assert res_201["nowcast_nis_headline_cpi"] == round(201.20 * (1.0 + (res_201["projected_mom_pct"] / 100.0)), 4)


def test_uncertainty_narrows_as_month_progresses():
    nowcaster = CPINowcaster()

    # Day 5 (early in month, high uncertainty)
    res_early = nowcaster.generate_synthetic_test_nowcast(date(2026, 8, 5))
    width_early = res_early["ci_upper_95"] - res_early["ci_lower_95"]

    # Day 28 (late in month, low uncertainty)
    res_late = nowcaster.generate_synthetic_test_nowcast(date(2026, 8, 28))
    width_late = res_late["ci_upper_95"] - res_late["ci_lower_95"]

    assert width_late < width_early, f"Expected {width_late} < {width_early}"


def test_execute_nowcasting_pipeline_callable():
    context = {"ds": "2026-08-18"}
    res = execute_nowcasting_pipeline(**context)
    assert isinstance(res, dict)
    assert "nowcast_headline_cpi" in res
    assert "projected_mom_pct" in res
    assert "nowcast_nis_headline_cpi" in res

