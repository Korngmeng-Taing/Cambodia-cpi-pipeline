"""
tests/test_hedonic_regression.py
────────────────────────────────
Unit tests for the hedonic regression module (Prompt 4).
No network/DB access; statsmodels is used for a tiny synthetic fit.
"""

import pandas as pd
import pytest

from pipeline import hedonic_regression as hr


def test_extract_specs_ram_and_storage():
    specs = hr.extract_specs("Samsung Galaxy S24 8GB RAM 256GB Storage")
    assert specs == {"RAM_GB": 8, "Storage_GB": 256}


def test_extract_specs_explicit_ram_with_standalone_storage():
    specs = hr.extract_specs("Samsung Galaxy A55 8GB RAM 128GB")
    assert specs == {"RAM_GB": 8, "Storage_GB": 128}


def test_extract_specs_missing_features_default_zero():
    specs = hr.extract_specs("Generic cable")
    assert specs == {"RAM_GB": 0, "Storage_GB": 0}


def test_fit_ols_rejects_tiny_sample():
    small = pd.DataFrame(
        {"RAM_GB": [1, 2], "Storage_GB": [16, 32], "raw_price": [100.0, 200.0]}
    )
    with pytest.raises(ValueError, match=">= 20"):
        hr.fit_ols(small)


def test_fit_ols_rank_deficiency_guard():
    # 25 identical spec rows -> rank deficient X matrix
    collinear = pd.DataFrame(
        {"RAM_GB": [8] * 25, "Storage_GB": [128] * 25, "raw_price": [500.0 + i for i in range(25)]}
    )
    with pytest.raises(ValueError, match="rank-deficient"):
        hr.fit_ols(collinear)


def test_compute_hedonic_adjusted_neutralizes_spec_upgrade():
    # Synthetic data where ln(price) = 4.0 + 0.05*RAM + 0.002*Storage (exact log-linear model).
    import numpy as np

    rows = []
    for ram in (4, 6, 8, 12, 16):
        for storage in (64, 128, 256, 512):
            log_p = 4.0 + 0.05 * ram + 0.002 * storage
            rows.append(
                {
                    "RAM_GB": ram,
                    "Storage_GB": storage,
                    "raw_price": float(np.exp(log_p)),
                }
            )
    df = pd.DataFrame(rows)
    fit = hr.fit_ols(df)
    assert fit["r2"] > 0.99

    base = {"RAM_GB": 8.0, "Storage_GB": 128.0}
    current = df.sample(3, random_state=1)
    adjusted = hr.compute_hedonic_adjusted(current, fit, base)

    # Every item revalued at baseline specs should equal the baseline predicted price.
    base_price = round(
        float(np.exp(4.0 + 0.05 * base["RAM_GB"] + 0.002 * base["Storage_GB"])), 2
    )
    for value in adjusted:
        assert value == pytest.approx(base_price, rel=1e-2)


def test_baseline_specs_uses_prior_month():
    df = pd.DataFrame(
        {
            "scrape_date": ["2026-07-10", "2026-07-20", "2026-08-01"],
            "RAM_GB": [4.0, 8.0, 16.0],
            "Storage_GB": [64.0, 128.0, 256.0],
            "raw_price": [100.0, 120.0, 160.0],
        }
    )
    base = hr.baseline_specs(df, "2026-08-18")
    assert base == {"RAM_GB": pytest.approx(6.0), "Storage_GB": pytest.approx(96.0)}


def test_persist_hedonic_adjusted_record_construction():
    current = pd.DataFrame(
        [
            {
                "scrape_date": "2026-08-18",
                "item_id": "phone_123",
                "store_slug": "samnangshop",
                "canonical_name": "iPhone 15 128GB",
                "raw_price": 800.0,
                "RAM_GB": 6,
                "Storage_GB": 128,
            }
        ]
    )
    adjusted = pd.Series([780.0], index=current.index)
    fit = {"r2": 0.95}

    class MockConn:
        def __init__(self):
            self.executed = []

        def execute(self, stmt, params):
            self.executed.append(params)

    class MockEngine:
        def begin(self):
            conn = MockConn()
            self.last_conn = conn
            from contextlib import contextmanager

            @contextmanager
            def _cm():
                yield conn

            return _cm()

    mock_engine = MockEngine()
    count = hr.persist_hedonic_adjusted(mock_engine, current, adjusted, fit, "2026-08-18")
    assert count == 1
    rec = mock_engine.last_conn.executed[0]
    assert rec["item_id"] == "phone_123"
    assert rec["store_slug"] == "samnangshop"
    assert rec["canonical_name"] == "iPhone 15 128GB"
    assert rec["hedonic_adjusted_price_khr"] == 780.0

