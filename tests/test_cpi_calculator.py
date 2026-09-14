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

    # Weighted Laspeyres: (17.230 * 120.0 + 8.450 * 100.0) / (17.230 + 8.450) = 113.419
    expected_div_index = (17.230 * 120.0 + 8.450 * 100.0) / (17.230 + 8.450)
    assert pytest.approx(div01["division_index"], 0.001) == expected_div_index
    # Ensure it's not the unweighted geometric mean (which would be sqrt(1.2 * 1.0) * 100 = 109.54)
    assert abs(div01["division_index"] - 109.5445) > 1.0


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
    assert len(remaining_ids) == 7, "All 7 valid items must be retained"






