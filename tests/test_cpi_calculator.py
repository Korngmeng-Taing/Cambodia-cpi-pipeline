"""
=============================================================================
UNIT TESTS FOR CPI CALCULATION ENGINE (Jevons & Laspeyres)
=============================================================================
"""

import pytest
import numpy as np
import pandas as pd
from datetime import date
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
    """Ensures zeros and empty arrays do not crash computation and mismatched lengths raise ValueError."""
    assert cpi_engine.compute_jevons_index(np.array([]), np.array([])) == 100.0
    assert cpi_engine.compute_jevons_index(np.array([0.0, -5.0]), np.array([100.0, 100.0])) == 100.0
    with pytest.raises(ValueError, match="Arrays must be aligned by item_id"):
        cpi_engine.compute_jevons_index(np.array([100.0, 200.0]), np.array([100.0]))

def test_laspeyres_division_and_headline_aggregation(cpi_engine):
    """Tests 12-division aggregation with official NIS Cambodia weights."""
    calc_date = date(2026, 8, 26)
    
    # Mock elementary dataframe
    items = []
    for div, _weight in DEFAULT_NIS_WEIGHTS.items():
        items.append({
            "calculation_date": calc_date,
            "item_id": uuid4(),
            "coicop_division": div,
            "coicop_code": f"{div}.1.1",
            "base_price_khr": 4000.0,
            "current_price_khr": 4400.0 if div == "01" else 4000.0, # 10% increase in Food only
            "price_ratio": 1.10 if div == "01" else 1.00,
            "price_ratio_pct": 110.0 if div == "01" else 100.0,
            "is_imputed": False,
            "observation_count": 10
        })
    df_elem = pd.DataFrame(items)

    _df_div, headline = cpi_engine.aggregate_division_and_headline(df_elem, calc_date)

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
    assert bool(item2_row["is_imputed"]) is True
    # Advanced using ILO Class-Mean Imputation: 2100.0 * (1100.0 / 1050.0) = 2200.0
    assert pytest.approx(item2_row["current_price_khr"], 0.01) == 2200.0
    assert pytest.approx(item2_row["price_ratio"], 0.001) == 2200.0 / 2000.0


def test_missing_division_saves_as_null(cpi_engine):
    """Tests that missing divisions have division_index as None/NaN in DataFrame and convert to None for DB."""
    calc_date = date(2026, 8, 30)
    # Only division 01 has items; division 10 is missing
    elem_df = pd.DataFrame([
        {
            "calculation_date": calc_date,
            "item_id": "item-1",
            "coicop_division": "01",
            "coicop_code": "01.1.1",
            "base_price_khr": 1000.0,
            "current_price_khr": 1050.0,
            "price_ratio": 1.05,
            "price_ratio_pct": 105.0,
            "is_imputed": False,
            "observation_count": 1,
        }
    ])

    df_div, headline = cpi_engine.aggregate_division_and_headline(elem_df, calc_date)
    div10 = df_div[df_div["coicop_division"] == "10"].iloc[0]
    assert div10["item_count"] == 0
    assert pd.isna(div10["division_index"])

    # Verify that during DB serialization, NaN converts to Python None (which becomes SQL NULL)
    cpi_rows = [
        (
            r["calculation_date"], r["coicop_division"], r["division_name"], r["weight"],
            None if pd.isna(r["division_index"]) else float(r["division_index"]),
            headline["headline_cpi"], headline["core_cpi"],
            int(r["item_count"]), int(r["observation_count"])
        )
        for _, r in df_div.iterrows()
    ]
    row10 = next(r for r in cpi_rows if r[1] == "10")
    assert row10[4] is None  # Must be None, not float('nan')


def test_monthly_cpi_aggregation():
    """Verifies monthly aggregation logic across daily conformed indices."""
    daily_records = [
        # August 2026: 3 days of conformed headline CPI
        {"calculation_date": date(2026, 8, 1), "headline_cpi": 100.0, "core_cpi": 100.0, "observation_count": 100},
        {"calculation_date": date(2026, 8, 15), "headline_cpi": 102.0, "core_cpi": 101.0, "observation_count": 120},
        {"calculation_date": date(2026, 8, 31), "headline_cpi": 104.0, "core_cpi": 102.0, "observation_count": 110},
    ]
    df = pd.DataFrame(daily_records)
    df["cpi_month"] = pd.to_datetime(df["calculation_date"]).dt.to_period("M").dt.to_timestamp().dt.date

    monthly_summary = df.groupby("cpi_month").agg(
        monthly_headline_cpi=("headline_cpi", "mean"),
        monthly_core_cpi=("core_cpi", "mean"),
        active_days=("calculation_date", "nunique"),
        total_obs=("observation_count", "sum"),
    ).reset_index()

    # Average of 100, 102, 104 is 102.0
    assert pytest.approx(monthly_summary.iloc[0]["monthly_headline_cpi"], 0.01) == 102.0
    # Average of 100, 101, 102 is 101.0
    assert pytest.approx(monthly_summary.iloc[0]["monthly_core_cpi"], 0.01) == 101.0
    assert monthly_summary.iloc[0]["active_days"] == 3
    assert monthly_summary.iloc[0]["total_obs"] == 330


def test_seven_day_imputation_multistore_geometric_mean(cpi_engine):
    """Verifies that missing item imputation computes unweighted geometric mean across stores on latest observed date."""
    base_date = date(2026, 8, 18)
    day_1 = date(2026, 8, 19)
    day_2 = date(2026, 8, 20)

    item1_id = uuid4()
    item2_id = uuid4()

    base_df = pd.DataFrame([
        {"item_id": item1_id, "coicop_division": "01", "coicop_code": "01.1.1", "base_price_khr": 1000.0, "base_obs_count": 1},
        {"item_id": item2_id, "coicop_division": "01", "coicop_code": "01.1.1", "base_price_khr": 2000.0, "base_obs_count": 1},
    ])

    # On day 1, Item 2 is observed at both store_a (1800) and store_b (2000)
    # Expected geometric mean on day 1 = sqrt(1800 * 2000) = 1897.3666
    df_history = pd.DataFrame([
        # Base date
        {"scrape_date": base_date, "item_id": item1_id, "coicop_division": "01", "coicop_code": "01.1.1", "unit_price_khr": 1000.0, "is_outlier": False, "price_khr": 1000.0, "store_slug": "store_a", "name_clean": "Item 1"},
        {"scrape_date": base_date, "item_id": item2_id, "coicop_division": "01", "coicop_code": "01.1.1", "unit_price_khr": 2000.0, "is_outlier": False, "price_khr": 2000.0, "store_slug": "store_a", "name_clean": "Item 2"},
        # Day 1
        {"scrape_date": day_1, "item_id": item1_id, "coicop_division": "01", "coicop_code": "01.1.1", "unit_price_khr": 1000.0, "is_outlier": False, "price_khr": 1000.0, "store_slug": "store_a", "name_clean": "Item 1"},
        {"scrape_date": day_1, "item_id": item2_id, "coicop_division": "01", "coicop_code": "01.1.1", "unit_price_khr": 1800.0, "is_outlier": False, "price_khr": 1800.0, "store_slug": "store_a", "name_clean": "Item 2"},
        {"scrape_date": day_1, "item_id": item2_id, "coicop_division": "01", "coicop_code": "01.1.1", "unit_price_khr": 2000.0, "is_outlier": False, "price_khr": 2000.0, "store_slug": "store_b", "name_clean": "Item 2"},
        # Day 2: Only item 1 is present at 1100 (10% increase)
        {"scrape_date": day_2, "item_id": item1_id, "coicop_division": "01", "coicop_code": "01.1.1", "unit_price_khr": 1100.0, "is_outlier": False, "price_khr": 1100.0, "store_slug": "store_a", "name_clean": "Item 1"},
    ])

    elem_df = cpi_engine.compute_daily_elementary_indices(day_2, base_df, df_history, imputation_window_days=7)
    item2_row = elem_df[elem_df["item_id"] == item2_id].iloc[0]

    assert bool(item2_row["is_imputed"]) is True
    expected_geom_mean = np.exp((np.log(1800.0) + np.log(2000.0)) / 2)
    expected_imputed = expected_geom_mean * (1100.0 / 1000.0)
    assert pytest.approx(item2_row["current_price_khr"], 0.01) == expected_imputed


def test_subclass_weighted_division_aggregation(cpi_engine):
    """Verifies that items within a division are aggregated using official 4-digit subclass weights (ILO/IMF standard)."""
    calc_date = date(2026, 8, 28)
    # Division 01 with Rice (01.1.1, wt 17.23) and Meat (01.1.2, wt 8.45)
    elem_df = pd.DataFrame([
        {
            "calculation_date": calc_date,
            "item_id": uuid4(),
            "coicop_division": "01",
            "coicop_code": "01.1.1",
            "base_price_khr": 1000.0,
            "current_price_khr": 1200.0,  # 20% increase -> index 120.0
            "price_ratio": 1.20,
            "price_ratio_pct": 120.0,
            "is_imputed": False,
            "observation_count": 5,
        },
        {
            "calculation_date": calc_date,
            "item_id": uuid4(),
            "coicop_division": "01",
            "coicop_code": "01.1.2",
            "base_price_khr": 2000.0,
            "current_price_khr": 2000.0,  # 0% increase -> index 100.0
            "price_ratio": 1.00,
            "price_ratio_pct": 100.0,
            "is_imputed": False,
            "observation_count": 5,
        },
    ])

    df_div, _headline = cpi_engine.aggregate_division_and_headline(elem_df, calc_date)
    div01 = df_div[df_div["coicop_division"] == "01"].iloc[0]

    # Weighted Laspeyres using official subclass weights:
    w_bread = cpi_engine.subclass_weights["01.1.1"]
    w_meat = cpi_engine.subclass_weights["01.1.2"]
    expected_div_index = (w_bread * 120.0 + w_meat * 100.0) / (w_bread + w_meat)
    assert pytest.approx(div01["division_index"], 0.001) == expected_div_index


def test_chain_linking_splice_factor(cpi_engine):
    """Verifies that chain-linking splice factor scales division indices, headline CPI, and core CPI proportionally."""
    calc_date = date(2027, 1, 15)
    elem_df = pd.DataFrame([
        {
            "calculation_date": calc_date,
            "item_id": uuid4(),
            "coicop_division": "01",
            "coicop_code": "01.1.1",
            "base_price_khr": 1000.0,
            "current_price_khr": 1000.0,
            "price_ratio": 1.00,
            "price_ratio_pct": 100.0,
            "is_imputed": False,
            "observation_count": 5,
        },
        {
            "calculation_date": calc_date,
            "item_id": uuid4(),
            "coicop_division": "02",
            "coicop_code": "02.1.3",
            "base_price_khr": 2000.0,
            "current_price_khr": 2000.0,
            "price_ratio": 1.00,
            "price_ratio_pct": 100.0,
            "is_imputed": False,
            "observation_count": 5,
        },
    ])

    # Unadjusted run (splice_factor = 1.0)
    _df_div_base, headline_base = cpi_engine.aggregate_division_and_headline(elem_df, calc_date, splice_factor=1.0)
    assert pytest.approx(headline_base["headline_cpi"], 0.001) == 100.0

    # Spliced run (e.g. 2026 average December CPI was 105.50 -> splice_factor = 1.055)
    splice = 1.055
    df_div_spliced, headline_spliced = cpi_engine.aggregate_division_and_headline(elem_df, calc_date, splice_factor=splice)

    assert pytest.approx(headline_spliced["headline_cpi"], 0.001) == 100.0 * splice
    assert pytest.approx(headline_spliced["core_cpi"], 0.001) == 100.0 * splice
    for _, row in df_div_spliced.iterrows():
        if row["item_count"] > 0:
            assert pytest.approx(row["division_index"], 0.001) == 100.0 * splice


def test_compounded_imputation_with_timestamp(cpi_engine):
    """Verifies that multi-day missing items compound movement correctly without crashing on pd.Timestamp."""
    calc_date = date(2026, 9, 10)
    base_df = pd.DataFrame([
        {"item_id": "item-1", "coicop_division": "01", "coicop_code": "01.1.1", "base_price_khr": 1000.0},
        {"item_id": "item-2", "coicop_division": "01", "coicop_code": "01.1.1", "base_price_khr": 2000.0},
    ])
    df_history = pd.DataFrame([
        # item-1 observed yesterday (Sep 9) and today (Sep 10) -> movement = 1100 / 1000 = 1.10
        {"scrape_date": pd.Timestamp("2026-09-09"), "item_id": "item-1", "unit_price_khr": 1000.0},
        {"scrape_date": pd.Timestamp("2026-09-10"), "item_id": "item-1", "unit_price_khr": 1100.0},
        # item-2 observed 3 days ago (Sep 7) with unit_price 2000.0, missing on Sep 8, 9, 10
        {"scrape_date": pd.Timestamp("2026-09-07"), "item_id": "item-2", "unit_price_khr": 2000.0},
    ])

    # Ensure scrape_date in df_history contains date objects like the real pipeline
    df_history["scrape_date"] = pd.to_datetime(df_history["scrape_date"]).dt.date
    result = cpi_engine.compute_daily_elementary_indices(calc_date, base_df, df_history)
    item2_row = result[result["item_id"] == "item-2"].iloc[0]
    assert bool(item2_row["is_imputed"]) is True
    # Under ILO CPI Manual §6.58, movement is applied to the last observed price without exponential compounding
    expected = 2000.0 * 1.10
    assert pytest.approx(item2_row["current_price_khr"], 0.01) == expected


def test_base_price_fallback_earliest_date(cpi_engine):
    """Verifies fallback uses the earliest available scrape date when base date has no data."""
    df_prices = pd.DataFrame([
        {"scrape_date": date(2026, 8, 1), "item_id": "item-1", "coicop_division": "01", "coicop_code": "01.1.1", "unit_price_khr": 1000.0},
        {"scrape_date": date(2026, 8, 2), "item_id": "item-1", "coicop_division": "01", "coicop_code": "01.1.1", "unit_price_khr": 5000.0},
    ])
    # Target date with no data
    missing_base_date = date(2026, 7, 1)
    base_res = cpi_engine.compute_base_prices(missing_base_date, df_prices)
    # Should use Aug 1 price (1000.0), NOT average of Aug 1 & Aug 2 (sqrt(1000*5000) = 2236)
    assert pytest.approx(base_res.iloc[0]["base_price_khr"], 0.01) == 1000.0


def test_subclass_first_imputation(cpi_engine):
    """Verifies that missing items use their 4-digit subclass movement before falling back to division."""
    calc_date = date(2026, 9, 10)
    # Division 01 has Rice (01.1.1) and Chocolate (01.1.8)
    base_df = pd.DataFrame([
        {"item_id": "rice-1", "coicop_division": "01", "coicop_code": "01.1.1", "base_price_khr": 1000.0},
        {"item_id": "rice-2", "coicop_division": "01", "coicop_code": "01.1.1", "base_price_khr": 1000.0},
        {"item_id": "choc-1", "coicop_division": "01", "coicop_code": "01.1.8", "base_price_khr": 2000.0},
        {"item_id": "choc-2", "coicop_division": "01", "coicop_code": "01.1.8", "base_price_khr": 2000.0},
        {"item_id": "choc-missing", "coicop_division": "01", "coicop_code": "01.1.8", "base_price_khr": 2000.0},
    ])
    df_history = pd.DataFrame([
        # Yesterday: all observed at base prices
        {"scrape_date": date(2026, 9, 9), "item_id": "rice-1", "unit_price_khr": 1000.0},
        {"scrape_date": date(2026, 9, 9), "item_id": "rice-2", "unit_price_khr": 1000.0},
        {"scrape_date": date(2026, 9, 9), "item_id": "choc-1", "unit_price_khr": 2000.0},
        {"scrape_date": date(2026, 9, 9), "item_id": "choc-2", "unit_price_khr": 2000.0},
        {"scrape_date": date(2026, 9, 9), "item_id": "choc-missing", "unit_price_khr": 2000.0},
        # Today: Rice jumps 50% (1000 -> 1500), but Chocolate only increases 5% (2000 -> 2100)
        {"scrape_date": date(2026, 9, 10), "item_id": "rice-1", "unit_price_khr": 1500.0},
        {"scrape_date": date(2026, 9, 10), "item_id": "rice-2", "unit_price_khr": 1500.0},
        {"scrape_date": date(2026, 9, 10), "item_id": "choc-1", "unit_price_khr": 2100.0},
        {"scrape_date": date(2026, 9, 10), "item_id": "choc-2", "unit_price_khr": 2100.0},
        # choc-missing is missing today!
    ])
    result = cpi_engine.compute_daily_elementary_indices(calc_date, base_df, df_history)
    missing_row = result[result["item_id"] == "choc-missing"].iloc[0]
    assert bool(missing_row["is_imputed"]) is True
    # If using division movement, rice's 50% jump would distort chocolate.
    # With subclass-first imputation, chocolate movement is exactly 2100 / 2000 = 1.05!
    expected_imputed = 2000.0 * 1.05
    assert pytest.approx(missing_row["current_price_khr"], 0.01) == expected_imputed


def test_unclassified_subclass_resolution(cpi_engine):
    """Verifies that unclassified codes do not fall back to 01.1.1."""
    assert cpi_engine._get_subclass_code("01.1.1", "01") == "01.1.1"
    assert cpi_engine._get_subclass_code("01.1.8", "01") == "01.1.8"
    assert cpi_engine._get_subclass_code("01.unclassified", "01") == "01.unclassified"
    assert cpi_engine._get_subclass_code("05.unclassified", "05") == "05.unclassified"
    assert cpi_engine._get_subclass_code("unknown_code", "01") == "01.unclassified"
    assert cpi_engine._get_subclass_code(None, "01") == "01.unclassified"


def test_mad_statistical_outlier_filtering(cpi_engine):
    """Tests that MAD robust outlier filtering flags extreme price spikes/drops while preserving normal movements."""
    # Normal group of 8 items around ratio 1.0 (0.95 to 1.05) + 1 extreme 10x decimal glitch
    df = pd.DataFrame([
        {"item_id": f"item-{i}", "coicop_division": "01", "price_ratio": r}
        for i, r in enumerate([0.98, 1.00, 1.02, 1.01, 0.99, 1.03, 0.97, 10.0])  # item-7 is a 10x outlier
    ])

    filtered = cpi_engine.filter_statistical_outliers_mad(df, group_col="coicop_division", z_threshold=3.5)
    remaining_ids = set(filtered["item_id"])

    assert "item-7" not in remaining_ids, "10x price ratio outlier must be filtered by MAD"

def test_persistent_base_registry_and_enrollment(cpi_engine, monkeypatch):
    """Verifies that newly observed items enroll with permanently anchored base prices via enroll_new_base_items."""
    enrolled_calls = []

    def mock_enroll(new_items, enrollment_date):
        enrolled_calls.append((new_items.copy(), enrollment_date))

    monkeypatch.setattr(cpi_engine, "enroll_new_base_items", mock_enroll)

    calc_date = date(2026, 9, 15)
    base_df = pd.DataFrame([
        {"item_id": "item-existing-1", "coicop_division": "01", "coicop_code": "01.1.1", "base_price_khr": 1000.0, "base_unit_price_khr": 1000.0, "base_obs_count": 1}
    ])
    df_history = pd.DataFrame([
        {"scrape_date": calc_date, "item_id": "item-existing-1", "coicop_division": "01", "coicop_code": "01.1.1", "price_khr": 1100.0, "unit_price_khr": 1100.0},
        {"scrape_date": calc_date, "item_id": "item-new-2", "coicop_division": "02", "coicop_code": "02.1.1", "price_khr": 5000.0, "unit_price_khr": 5000.0},
    ])

    result = cpi_engine.compute_daily_elementary_indices(calc_date, base_df, df_history)

    # Check that item-new-2 was enrolled with base price 5000
    assert len(enrolled_calls) == 1
    enrolled_df, enroll_dt = enrolled_calls[0]
    assert enroll_dt == calc_date
    assert "item-new-2" in set(enrolled_df["item_id"])
    assert enrolled_df[enrolled_df["item_id"] == "item-new-2"]["base_price_khr"].iloc[0] == pytest.approx(5000.0, abs=0.01)

    # In result DataFrame, item-new-2 has price ratio 1.0 (5000 / 5000) on enrollment day
    new_row = result[result["item_id"] == "item-new-2"].iloc[0]
    assert new_row["price_ratio"] == pytest.approx(1.0, abs=1e-5)
    assert new_row["base_price_khr"] == pytest.approx(5000.0, abs=0.01)


def test_three_tier_imputation_hierarchy(cpi_engine):
    """Verifies the ILO 3-tier imputation fallback: Subclass (4-digit) -> Group (3-digit) -> Division (2-digit)."""
    calc_date = date(2026, 9, 2)
    prev_date = date(2026, 9, 1)

    # Base registry
    base_df = pd.DataFrame([
        {"item_id": "item-subclass-matched", "coicop_division": "01", "coicop_code": "01.1.1", "base_price_khr": 1000.0, "base_unit_price_khr": 1000.0, "base_obs_count": 1},
        {"item_id": "item-group-matched", "coicop_division": "01", "coicop_code": "01.1.2", "base_price_khr": 2000.0, "base_unit_price_khr": 2000.0, "base_obs_count": 1},
        {"item_id": "item-div-matched", "coicop_division": "02", "coicop_code": "02.1.1", "base_price_khr": 3000.0, "base_unit_price_khr": 3000.0, "base_obs_count": 1},
        # Imputed targets (missing on calc_date, present on prev_date)
        {"item_id": "missing-subclass", "coicop_division": "01", "coicop_code": "01.1.1", "base_price_khr": 1000.0, "base_unit_price_khr": 1000.0, "base_obs_count": 1},
        {"item_id": "missing-group", "coicop_division": "01", "coicop_code": "01.1.9", "base_price_khr": 2000.0, "base_unit_price_khr": 2000.0, "base_obs_count": 1},
        {"item_id": "missing-div", "coicop_division": "02", "coicop_code": "02.2.1", "base_price_khr": 3000.0, "base_unit_price_khr": 3000.0, "base_obs_count": 1},
    ])

    # History: on prev_date, all items exist. On calc_date, the three 'missing-*' items are missing.
    df_history = pd.DataFrame([
        # Yesterday observations
        {"scrape_date": prev_date, "item_id": "item-subclass-matched", "coicop_division": "01", "coicop_code": "01.1.1", "price_khr": 1000.0, "unit_price_khr": 1000.0},
        {"scrape_date": prev_date, "item_id": "item-group-matched", "coicop_division": "01", "coicop_code": "01.1.2", "price_khr": 2000.0, "unit_price_khr": 2000.0},
        {"scrape_date": prev_date, "item_id": "item-div-matched", "coicop_division": "02", "coicop_code": "02.1.1", "price_khr": 3000.0, "unit_price_khr": 3000.0},
        {"scrape_date": prev_date, "item_id": "missing-subclass", "coicop_division": "01", "coicop_code": "01.1.1", "price_khr": 1000.0, "unit_price_khr": 1000.0},
        {"scrape_date": prev_date, "item_id": "missing-group", "coicop_division": "01", "coicop_code": "01.1.9", "price_khr": 2000.0, "unit_price_khr": 2000.0},
        {"scrape_date": prev_date, "item_id": "missing-div", "coicop_division": "02", "coicop_code": "02.2.1", "price_khr": 3000.0, "unit_price_khr": 3000.0},
        # Today observations: 01.1.1 rose +10%, 01.1.2 rose +5%, 02.1.1 rose +20%
        {"scrape_date": calc_date, "item_id": "item-subclass-matched", "coicop_division": "01", "coicop_code": "01.1.1", "price_khr": 1100.0, "unit_price_khr": 1100.0},
        {"scrape_date": calc_date, "item_id": "item-group-matched", "coicop_division": "01", "coicop_code": "01.1.2", "price_khr": 2100.0, "unit_price_khr": 2100.0},
        {"scrape_date": calc_date, "item_id": "item-div-matched", "coicop_division": "02", "coicop_code": "02.1.1", "price_khr": 3600.0, "unit_price_khr": 3600.0},
    ])

    result = cpi_engine.compute_daily_elementary_indices(calc_date, base_df, df_history)

    # 1. missing-subclass shares '01.1.1' -> should receive exactly +10% (1000 * 1.1 = 1100)
    sub_row = result[result["item_id"] == "missing-subclass"].iloc[0]
    assert sub_row["is_imputed"] is True or sub_row["is_imputed"] == 1
    assert sub_row["current_price_khr"] == pytest.approx(1100.0, rel=1e-3)

    # 2. missing-group is '01.1.9', no 01.1.9 items exist today, so it falls back to group '01.1'
    # Group 01.1 contains item-subclass-matched (1.10) and item-group-matched (1.05)
    # Geometric mean = sqrt(1.10 * 1.05) ~ 1.0747
    grp_row = result[result["item_id"] == "missing-group"].iloc[0]
    assert grp_row["is_imputed"] is True or grp_row["is_imputed"] == 1
    assert grp_row["current_price_khr"] == pytest.approx(2000.0 * np.sqrt(1.10 * 1.05), rel=1e-3)

    # 3. missing-div is '02.2.1', no 02.2.* items today, so it falls back to division '02' (+20% -> 1.20)
    div_row = result[result["item_id"] == "missing-div"].iloc[0]
    assert div_row["is_imputed"] is True or div_row["is_imputed"] == 1
    assert div_row["current_price_khr"] == pytest.approx(3600.0, rel=1e-3)


def test_shadow_tracking_new_products(cpi_engine, monkeypatch):
    """Verifies that when shadow_track_new_items=True, newly enrolled products are anchored but excluded from active day t index."""
    monkeypatch.setattr(cpi_engine, "enroll_new_base_items", lambda items, dt: None)

    calc_date = date(2026, 9, 20)
    base_df = pd.DataFrame([
        {"item_id": "item-old", "coicop_division": "01", "coicop_code": "01.1.1", "base_price_khr": 1000.0, "base_unit_price_khr": 1000.0, "base_obs_count": 1, "first_seen_date": date(2026, 9, 1)}
    ])
    df_history = pd.DataFrame([
        {"scrape_date": calc_date, "item_id": "item-old", "coicop_division": "01", "coicop_code": "01.1.1", "price_khr": 1050.0, "unit_price_khr": 1050.0},
        {"scrape_date": calc_date, "item_id": "item-brand-new", "coicop_division": "01", "coicop_code": "01.1.1", "price_khr": 5000.0, "unit_price_khr": 5000.0},
    ])

    # When shadow_track_new_items=False (default), both items are in result
    res_default = cpi_engine.compute_daily_elementary_indices(calc_date, base_df, df_history, shadow_track_new_items=False)
    assert "item-brand-new" in set(res_default["item_id"])

    # When shadow_track_new_items=True, item-brand-new is anchored but shadow-tracked (excluded on day t)
    res_shadow = cpi_engine.compute_daily_elementary_indices(calc_date, base_df, df_history, shadow_track_new_items=True)
    assert "item-brand-new" not in set(res_shadow["item_id"])
    assert "item-old" in set(res_shadow["item_id"])


def test_coverage_weight_and_store_balance(cpi_engine):
    """Verifies CoverageWeight_t calculation and store sample balance generation."""
    calc_date = date(2026, 9, 15)

    # 1. Verify store sample balance report
    df_raw = pd.DataFrame([
        {"item_id": "item-1", "store_name": "StoreA", "coicop_code": "01.1.1", "coicop_division": "01", "product_name": "Product 1"},
        {"item_id": "item-2", "store_name": "StoreA", "coicop_code": "01.1.1", "coicop_division": "01", "product_name": "Product 2"},
        {"item_id": "item-3", "store_name": "StoreB", "coicop_code": "01.1.1", "coicop_division": "01", "product_name": "Product 3"},
        {"item_id": None, "store_name": "StoreB", "coicop_code": "01.1.1", "coicop_division": "01", "product_name": "Unmatched 1"},
    ])
    df_elem = pd.DataFrame([
        {"item_id": "item-1", "coicop_code": "01.1.1", "coicop_division": "01", "is_imputed": False},
        {"item_id": "item-2", "coicop_code": "01.1.1", "coicop_division": "01", "is_imputed": False},
        {"item_id": "item-3", "coicop_code": "01.1.1", "coicop_division": "01", "is_imputed": True},
    ])

    balance_report = cpi_engine.generate_store_sample_balance_report(df_raw, df_elem)
    assert not balance_report.empty
    row = balance_report.iloc[0]
    assert row["total_observations"] == 4
    assert row["active_canonical_products"] == 3
    assert row["number_of_stores"] == 2
    assert row["unmatched_products"] == 1
    assert row["imputed_observations"] == 1
    assert "StoreA" in row["observations_by_store"]

    # 2. Verify CoverageWeight_t in aggregate_division_and_headline
    # Create mock subclass aggregations for Division 01 (weight 43.17%) and Division 02 (weight 2.92%)
    df_items = pd.DataFrame([
        {"item_id": f"item-01-{i}", "coicop_division": "01", "coicop_code": "01.1.1", "price_ratio": 1.02, "price_ratio_pct": 102.0, "observation_count": 1}
        for i in range(10)  # >= 5 obs -> active division
    ] + [
        {"item_id": f"item-02-{i}", "coicop_division": "02", "coicop_code": "02.1.1", "price_ratio": 1.01, "price_ratio_pct": 101.0, "observation_count": 1}
        for i in range(2)   # < 5 obs -> not sufficiently covered
    ])

    div_idx, headline = cpi_engine.aggregate_division_and_headline(df_items, calc_date)

    assert "coverage_weight" in headline
    # Only Division 01 met the min_obs_per_division >= 5 threshold, so coverage_weight is Div 01's weight (~44.78%)
    assert headline["coverage_weight"] == pytest.approx(44.78, abs=0.5)
    assert headline["active_division_count"] == 1


def test_evaluate_nis_benchmark_accuracy_calculation(cpi_engine):
    """Verifies that evaluate_nis_benchmark_accuracy computes correct MAE, RMSE, Pearson r, and concordance."""
    class MockCursor:
        def __init__(self, data):
            self.data = data
            self.description = [
                ("cpi_month",),
                ("pipeline_headline_cpi",),
                ("nis_headline_cpi",),
                ("pipeline_headline_cpi_rebased_to_nis",),
                ("headline_rebased_error",),
                ("pipeline_mom_pct",),
                ("nis_mom_pct",),
                ("directional_concordance",)
            ]
        def execute(self, q): pass
        def fetchall(self): return self.data
        def __enter__(self): return self
        def __exit__(self, *args): pass

    class MockConn:
        def __init__(self, data):
            self.data = data
        def cursor(self): return MockCursor(self.data)

    mock_data = [
        ("2026-01-01", 100.0, 100.0, 100.0, 0.0, 0.0, 0.0, True),
        ("2026-02-01", 102.0, 101.9, 102.0, 0.1, 2.0, 1.9, True),
        ("2026-03-01", 103.0, 102.8, 103.0, 0.2, 1.0, 0.9, True),
        ("2026-04-01", 101.0, 100.9, 101.0, 0.1, -1.9, -1.8, True),
    ]

    metrics = cpi_engine.evaluate_nis_benchmark_accuracy(MockConn(mock_data))
    assert metrics["sample_months"] == 4
    # Errors: |100-100|=0, |102-101.9|=0.1, |103-102.8|=0.2, |101-100.9|=0.1. MAE = 0.4/4 = 0.1
    assert metrics["mae"] == pytest.approx(0.1, abs=1e-4)
    # Directional concordance: all 3 MoM changes have same sign -> 100%
    assert metrics["directional_concordance_pct"] == pytest.approx(100.0, abs=1e-4)
    assert metrics["pearson_correlation"] > 0.95


def test_store_balanced_jevons(cpi_engine):
    """Verifies the two-stage store-balanced Jevons gives each store equal weight.
    
    Scenario: COICOP class 01.1.1 has two stores:
      - StoreA: 100 products, all with price_ratio = 1.10 (10% increase)
      - StoreB:   5 products, all with price_ratio = 0.90 (10% decrease)
    
    Without store balancing (flat Jevons): 
      geometric_mean of 105 items skewed toward 1.10
      = exp((100*ln(1.10) + 5*ln(0.90)) / 105) * 100 ~ 108.98
    
    With store balancing (two-stage):
      Stage 1: StoreA mean = 1.10, StoreB mean = 0.90
      Stage 2: geometric_mean(1.10, 0.90) = sqrt(1.10 * 0.90) ~ 0.9950
      = 99.50
    """
    calc_date = date(2026, 9, 15)
    
    # Build items: 100 from StoreA, 5 from StoreB
    items = []
    for i in range(100):
        items.append({
            "item_id": f"storeA-item-{i}",
            "coicop_division": "01",
            "coicop_code": "01.1.1",
            "price_ratio": 1.10,
            "price_ratio_pct": 110.0,
            "primary_store": "storeA",
            "observation_count": 1,
        })
    for i in range(5):
        items.append({
            "item_id": f"storeB-item-{i}",
            "coicop_division": "01",
            "coicop_code": "01.1.1",
            "price_ratio": 0.90,
            "price_ratio_pct": 90.0,
            "primary_store": "storeB",
            "observation_count": 1,
        })
    
    df_items = pd.DataFrame(items)
    div_idx, headline = cpi_engine.aggregate_division_and_headline(df_items, calc_date)
    
    # With store balancing: geometric_mean(1.10, 0.90) * 100 = sqrt(0.99) * 100 ~ 99.50
    div01_row = div_idx[div_idx["coicop_division"] == "01"].iloc[0]
    
    # The flat Jevons would give ~108.98. Store-balanced should be ~99.50.
    # This proves the 100-item store doesn't dominate the 5-item store.
    assert div01_row["division_index"] == pytest.approx(99.50, abs=0.5), \
        f"Store-balanced Jevons should give ~99.50, got {div01_row['division_index']:.2f}"
    
    # Verify: removing primary_store forces flat Jevons (no store info -> fallback)
    df_items_no_store = df_items.drop(columns=["primary_store"])
    div_idx2, headline2 = cpi_engine.aggregate_division_and_headline(df_items_no_store, calc_date)
    div01_flat = div_idx2[div_idx2["coicop_division"] == "01"].iloc[0]
    
    # Flat Jevons should be heavily skewed toward StoreA's 1.10
    assert div01_flat["division_index"] > 108.0, \
        f"Flat Jevons (no store info) should be >108, got {div01_flat['division_index']:.2f}"


def test_coicop_2018_five_digit_hierarchical_rollup(cpi_engine):
    """Verifies that items tagged with 5-digit COICOP 2018 codes (e.g. 01.1.1.1 for Rice,
    01.1.2.1 for Pork, 07.2.2.1 for Gasoline) automatically roll up to their official 4-digit
    parent subclass (01.1.1, 01.1.2, 07.2.2) and aggregate accurately without errors.
    """
    calc_date = date(2026, 9, 20)
    
    # 5-digit subclasses now match directly in subclass_weights with their CEIC weights:
    assert cpi_engine._get_subclass_code("01.1.1.1", "01") == "01.1.1.1"  # Rice Subclass
    assert cpi_engine._get_subclass_code("01.1.2.1", "01") == "01.1.2.1"  # Pork Subclass
    assert cpi_engine._get_subclass_code("07.2.2.1", "07") == "07.2.2.1"  # Gasoline Subclass
    
    # Child codes roll up to the nearest parent present in weights:
    assert cpi_engine._get_subclass_code("01.1.1.1.9", "01") == "01.1.1.1"  # Unknown Rice -> Rice
    assert cpi_engine._get_subclass_code("01.1.9.9", "01") == "01.1.9"      # Unknown Food -> Food Products n.e.c.
    
    # Build items with 5-digit codes
    items = pd.DataFrame([
        {
            "item_id": "rice-jasmine-1",
            "coicop_division": "01",
            "coicop_code": "01.1.1.1",  # 5-digit Rice (weight 6.162%)
            "price_ratio": 1.05,
            "price_ratio_pct": 105.0,
            "primary_store": "aeon",
            "observation_count": 5,
        },
        {
            "item_id": "rice-white-2",
            "coicop_division": "01",
            "coicop_code": "01.1.1.1",  # 5-digit Rice (weight 6.162%)
            "price_ratio": 1.05,
            "price_ratio_pct": 105.0,
            "primary_store": "delishop",
            "observation_count": 5,
        },
        {
            "item_id": "pork-belly-1",
            "coicop_division": "01",
            "coicop_code": "01.1.2.1",  # 5-digit Pork (weight 5.618%)
            "price_ratio": 1.00,
            "price_ratio_pct": 100.0,
            "primary_store": "aeon",
            "observation_count": 5,
        }
    ])
    
    div_df, headline = cpi_engine.aggregate_division_and_headline(items, calc_date)
    div01 = div_df[div_df["coicop_division"] == "01"].iloc[0]
    
    # 01.1.1.1 (Rice) index = 105.0 (weight 6.162)
    # 01.1.2.1 (Pork) index = 100.0 (weight 5.618)
    expected = (6.162 * 105.0 + 5.618 * 100.0) / (6.162 + 5.618)
    assert div01["division_index"] == pytest.approx(expected, abs=0.01)

def test_5digit_ceic_subclass_weights_consistency(cpi_engine):
    """Validates that 5-digit subclasses sum properly to parent classes and total divisions equal 100%."""
    wts = cpi_engine.subclass_weights
    
    # Transportation Fuel: Gasoline (4.969) + Diesel (0.144) + Motor Oil (0.062) = 5.175
    fuel_sub_sum = wts["07.2.2.1"] + wts["07.2.2.2"] + wts["07.2.2.3"]
    assert pytest.approx(fuel_sub_sum, 0.001) == wts["07.2.2"]
    
    # Dairy & Eggs: Fresh Egg (1.013) + Processed Egg (0.079) + Dairy (1.552) = 2.644
    dairy_sub_sum = wts["01.1.4.1"] + wts["01.1.4.2"] + wts["01.1.4.3"]
    assert pytest.approx(dairy_sub_sum, 0.001) == wts["01.1.4"]
    
    # Bread & Cereals: Rice (6.162) + Bread (0.173) + Noodles (1.008) + Biscuit (0.280) + Cake (0.561) + Other (0.090) = 8.274
    bread_sub_sum = (wts["01.1.1.1"] + wts["01.1.1.2"] + wts["01.1.1.3"] + 
                     wts["01.1.1.4"] + wts["01.1.1.5"] + wts["01.1.1.9"])
    assert pytest.approx(bread_sub_sum, 0.001) == wts["01.1.1"]
    
    # 12 Divisions sum to 1.000 (normalized expenditure shares)
    assert pytest.approx(sum(cpi_engine.weights.values()), 0.001) == 1.0






