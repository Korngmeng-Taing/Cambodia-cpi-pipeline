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


def test_extract_specs_missing_features_default_zero():
    specs = hr.extract_specs("Generic cable")
    assert specs == {"RAM_GB": 0, "Storage_GB": 0}


def test_fit_ols_rejects_tiny_sample():
    small = pd.DataFrame({"RAM_GB": [1, 2], "Storage_GB": [16, 32], "raw_price": [100.0, 200.0]})
    with pytest.raises(ValueError, match=">= 20"):
        hr.fit_ols(small)


def test_compute_hedonic_adjusted_neutralizes_spec_upgrade():
    # Synthetic data where ln(price) = 4.0 + 0.05*RAM + 0.002*Storage (exact log-linear model).
    import numpy as np
    rows = []
    for ram in (4, 6, 8, 12, 16):
        for storage in (64, 128, 256, 512):
            log_p = 4.0 + 0.05 * ram + 0.002 * storage
            rows.append({"RAM_GB": ram, "Storage_GB": storage,
                         "raw_price": float(np.exp(log_p))})
    df = pd.DataFrame(rows)
    fit = hr.fit_ols(df)
    assert fit["r2"] > 0.99

    base = {"RAM_GB": 8.0, "Storage_GB": 128.0}
    current = df.sample(3, random_state=1)
    adjusted = hr.compute_hedonic_adjusted(current, fit, base)

    # Every item revalued at baseline specs should equal the baseline predicted price.
    base_price = round(float(np.exp(4.0 + 0.05 * base["RAM_GB"] + 0.002 * base["Storage_GB"])), 2)
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
