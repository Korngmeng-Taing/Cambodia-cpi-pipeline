"""
tests/test_geks_calculator.py
─────────────────────────────
Unit tests for multilateral GEKS-Törnqvist price index calculation.
"""

import pandas as pd
import pytest

from pipeline.geks_calculator import GEKSCalculator


def test_bilateral_tornqvist_exact_shift():
    calc = GEKSCalculator()

    # Period 0: Item A=100, Item B=200
    p0 = pd.Series({"item_A": 100.0, "item_B": 200.0})
    # Period 1: Item A=110 (+10%), Item B=220 (+10%)
    p1 = pd.Series({"item_A": 110.0, "item_B": 220.0})

    rel, n_match = calc.calculate_bilateral_tornqvist(p0, p1)
    assert n_match == 2
    assert pytest.approx(rel, rel=1e-4) == 1.10


def test_bilateral_tornqvist_with_churn():
    calc = GEKSCalculator()

    # Period 0 has items A, B, C
    p0 = pd.Series({"item_A": 10.0, "item_B": 20.0, "item_C": 30.0})
    # Period 1 has items B, C, D (A dropped, D entered)
    p1 = pd.Series({"item_B": 22.0, "item_C": 33.0, "item_D": 50.0})

    # Matched items are B (+10%) and C (+10%)
    rel, n_match = calc.calculate_bilateral_tornqvist(p0, p1)
    assert n_match == 2
    assert pytest.approx(rel, rel=1e-4) == 1.10


def test_multilateral_geks_transitivity_and_circularity():
    calc = GEKSCalculator()

    # 3 periods of prices
    # Period 1 -> Period 2: +10%
    # Period 2 -> Period 3: +5%
    period_prices = {
        "2026-08-01": pd.Series({"item_1": 100.0, "item_2": 50.0}),
        "2026-08-02": pd.Series({"item_1": 110.0, "item_2": 55.0}),
        "2026-08-03": pd.Series({"item_1": 115.5, "item_2": 57.75}),
    }

    results = calc.calculate_multilateral_geks(period_prices, base_period="2026-08-01")

    assert "2026-08-01" in results
    assert "2026-08-02" in results
    assert "2026-08-03" in results

    assert results["2026-08-01"]["index_value"] == 100.0
    assert pytest.approx(results["2026-08-02"]["index_value"], rel=1e-3) == 110.0
    assert pytest.approx(results["2026-08-03"]["index_value"], rel=1e-3) == 115.5


def test_multilateral_geks_empty():
    calc = GEKSCalculator()
    res = calc.calculate_multilateral_geks({})
    assert res == {}
