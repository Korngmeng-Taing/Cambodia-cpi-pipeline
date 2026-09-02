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
    assert "projected_yoy_pct" in res

    # Check 95% Confidence Interval structure (ci_lower < cpi < ci_upper)
    assert res["ci_lower_95"] <= res["nowcast_headline_cpi"] <= res["ci_upper_95"]


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
