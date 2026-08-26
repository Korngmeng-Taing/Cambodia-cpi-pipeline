"""
=============================================================================
UNIT TESTS FOR CPI CALCULATION ENGINE (Jevons & Laspeyres)
=============================================================================
"""

import pytest
import numpy as np
import pandas as pd
from datetime import date, timedelta
from uuid import uuid4

from pipeline.cpi_calculator import CPICalculationEngine, DEFAULT_NIS_WEIGHTS

@pytest.fixture
def cpi_engine():
    return CPICalculationEngine()

def test_jevons_index_formula(cpi_engine):
    """Verifies Diewert (1995) time-reversal & geometric mean property."""
    base_prices = np.array([1000.0, 2000.0, 5000.0])
    # Case 1: Prices unchanged
    assert pytest.approx(cpi_engine.compute_jevons_index(base_prices, base_prices), 0.01) == 100.0

    # Case 2: All prices increase by 10%
    cur_prices = base_prices * 1.10
    assert pytest.approx(cpi_engine.compute_jevons_index(cur_prices, base_prices), 0.01) == 110.0

    # Case 3: Oscillating prices (Item A * 2, Item B * 0.5) -> geometric mean should be 1.0 (100.0)
    p0 = np.array([100.0, 100.0])
    p1 = np.array([200.0, 50.0])
    assert pytest.approx(cpi_engine.compute_jevons_index(p1, p0), 0.01) == 100.0

def test_jevons_zero_and_empty_handling(cpi_engine):
    """Ensures zeros and empty arrays do not crash computation."""
    assert cpi_engine.compute_jevons_index(np.array([]), np.array([])) == 100.0
    assert cpi_engine.compute_jevons_index(np.array([0.0, -5.0]), np.array([100.0])) == 100.0

def test_laspeyres_division_and_headline_aggregation(cpi_engine):
    """Tests 12-division aggregation with official NIS Cambodia weights."""
    calc_date = date(2026, 8, 26)
    
    # Mock elementary dataframe
    items = []
    for div, weight in DEFAULT_NIS_WEIGHTS.items():
        items.append({
            "calculation_date": calc_date,
            "item_id": uuid4(),
            "coicop_division": div,
            "coicop_code": f"{div}.1.1",
            "base_price_khr": 4000.0,
            "current_price_khr": 4400.0 if div == "01" else 4000.0, # 10% increase in Food only
            "price_ratio": 1.10 if div == "01" else 1.00,
            "elementary_index": 110.0 if div == "01" else 100.0,
            "is_imputed": False,
            "observation_count": 10
        })
    df_elem = pd.DataFrame(items)

    df_div, headline = cpi_engine.aggregate_division_and_headline(df_elem, calc_date)

    # Food weight is 44.8%, Food index is 110.0, others are 100.0
    # Expected Headline CPI = 100.0 + (0.448 * 10.0) = 104.48
    assert pytest.approx(headline["headline_cpi"], 0.01) == 104.48
    
    # Core CPI excludes Food, so Core CPI should be 100.00
    assert pytest.approx(headline["core_cpi"], 0.01) == 100.00

def test_seven_day_imputation(cpi_engine):
    """Tests carry-forward imputation for missing items within 7 days."""
    base_date = date(2026, 8, 18)
    day_1 = date(2026, 8, 19)
    day_2 = date(2026, 8, 20) # Item 2 missing on day 2

    item1_id = uuid4()
    item2_id = uuid4()

    base_df = pd.DataFrame([
        {"item_id": item1_id, "coicop_division": "01", "coicop_code": "01.1.1", "base_price_khr": 1000.0, "base_obs_count": 1},
        {"item_id": item2_id, "coicop_division": "01", "coicop_code": "01.1.1", "base_price_khr": 2000.0, "base_obs_count": 1},
    ])

    df_history = pd.DataFrame([
        # Base date
        {"scrape_date": base_date, "item_id": item1_id, "coicop_division": "01", "coicop_code": "01.1.1", "unit_price_khr": 1000.0, "is_outlier": False, "price_khr": 1000.0, "store_slug": "aeon", "name_clean": "Item 1"},
        {"scrape_date": base_date, "item_id": item2_id, "coicop_division": "01", "coicop_code": "01.1.1", "unit_price_khr": 2000.0, "is_outlier": False, "price_khr": 2000.0, "store_slug": "aeon", "name_clean": "Item 2"},
        # Day 1
        {"scrape_date": day_1, "item_id": item1_id, "coicop_division": "01", "coicop_code": "01.1.1", "unit_price_khr": 1050.0, "is_outlier": False, "price_khr": 1050.0, "store_slug": "aeon", "name_clean": "Item 1"},
        {"scrape_date": day_1, "item_id": item2_id, "coicop_division": "01", "coicop_code": "01.1.1", "unit_price_khr": 2100.0, "is_outlier": False, "price_khr": 2100.0, "store_slug": "aeon", "name_clean": "Item 2"},
        # Day 2: Only item 1 is present
        {"scrape_date": day_2, "item_id": item1_id, "coicop_division": "01", "coicop_code": "01.1.1", "unit_price_khr": 1100.0, "is_outlier": False, "price_khr": 1100.0, "store_slug": "aeon", "name_clean": "Item 1"},
    ])

    elem_df = cpi_engine.compute_daily_elementary_indices(day_2, base_df, df_history, imputation_window_days=7)

    assert len(elem_df) == 2
    item2_row = elem_df[elem_df["item_id"] == item2_id].iloc[0]
    assert item2_row["is_imputed"] == True
    # Carried forward from day 1 price of 2100.0
    assert item2_row["current_price_khr"] == 2100.0
    assert pytest.approx(item2_row["price_ratio"], 0.001) == 2100.0 / 2000.0
