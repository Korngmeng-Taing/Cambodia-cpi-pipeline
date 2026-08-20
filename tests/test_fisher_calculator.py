"""
tests/test_fisher_calculator.py
───────────────────────────────
Unit tests for Superlative Fisher Ideal Price Index calculator.
"""

import pandas as pd
import pytest

from pipeline.fisher_calculator import FisherCalculator


def test_fisher_calculation_exact():
    # Base period prices
    p0 = pd.Series({"item_pork": 20000.0, "item_chicken": 10000.0})
    # Current period prices (Pork doubled +100%, Chicken stayed same 0%)
    p1 = pd.Series({"item_pork": 40000.0, "item_chicken": 10000.0})

    # Base period expenditure weights (e.g. 10kg pork, 10kg chicken -> 200k/300k, 100k/300k)
    w0 = pd.Series({"item_pork": 200000.0, "item_chicken": 100000.0})
    # Current period expenditure weights (e.g. 2kg pork, 18kg chicken -> 80k/260k, 180k/260k)
    w1 = pd.Series({"item_pork": 80000.0, "item_chicken": 180000.0})

    res = FisherCalculator.calculate_bilateral_fisher(p0, p1, w0, w1)

    assert res["matched_items_count"] == 2
    assert res["laspeyres_index"] == pytest.approx(166.6667, rel=1e-3)
    assert res["paasche_index"] == pytest.approx(118.1818, rel=1e-3)
    assert res["fisher_index"] == pytest.approx(140.3473, rel=1e-3)
    # Substitution bias should be positive (Laspeyres > Fisher)
    assert res["substitution_bias_pct"] > 20.0


def test_fisher_time_reversal_property():
    """Fisher index must satisfy the time reversal test: P_01 * P_10 = 1.0"""
    p0 = pd.Series({"item_1": 100.0, "item_2": 200.0, "item_3": 300.0})
    p1 = pd.Series({"item_1": 150.0, "item_2": 180.0, "item_3": 450.0})

    res_forward = FisherCalculator.calculate_bilateral_fisher(p0, p1)
    res_backward = FisherCalculator.calculate_bilateral_fisher(p1, p0)

    p_01 = res_forward["fisher_index"] / 100.0
    p_10 = res_backward["fisher_index"] / 100.0

    assert p_01 * p_10 == pytest.approx(1.0, rel=1e-5)


def test_fisher_unweighted_empty():
    p0 = pd.Series({}, dtype=float)
    p1 = pd.Series({}, dtype=float)

    res = FisherCalculator.calculate_bilateral_fisher(p0, p1)
    assert res["matched_items_count"] == 0
    assert res["fisher_index"] == 100.0
