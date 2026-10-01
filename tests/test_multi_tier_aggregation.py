"""
Tests for Case A (Class with Subclasses) and Case B (Class without Subclasses),
Multi-Tier Aggregation (EA -> Class -> Group -> Division -> Headline CPI),
and Missing Data Weight Renormalization.
"""
import pytest
import numpy as np
import pandas as pd
from datetime import date

from pipeline.coicop_hierarchy import COICOPHierarchy
from pipeline.cpi_calculator import CPICalculationEngine

@pytest.fixture
def cpi_engine():
    return CPICalculationEngine()

def test_case_a_and_case_b_calculation_flow(cpi_engine):
    """
    Validates:
    - Case A: Class 01.1.1 (Bread & Cereals) with Subclasses.
    - Case B: Class 01.1.5 (Oils & Fats) without Subclasses.
    - Higher-level aggregation into Group 01.1, Division 01, and Headline CPI.
    - Verification that parent weights (Rice 6.162%) are NOT double-counted.
    """
    calc_date = date(2026, 9, 27)
    
    # Construct synthetic items for:
    # 1. 01.1.1.1.1 (Jasmine Rice): index = 110.0 (weight = 3.052)
    # 2. 01.1.1.1.2 (White Rice): index = 105.0 (weight = 2.681)
    # 3. 01.1.1.2 (Bread): index = 100.0 (weight = 0.173)
    # (Other subclasses of 01.1.1 missing -> reweighted over available weights)
    # 4. 01.1.5 (Oils and Fats - Case B): index = 120.0 (weight = 0.920)
    
    items = pd.DataFrame([
        # Jasmine Rice (Store A & Store B)
        {
            "item_id": "rice-j1",
            "coicop_division": "01",
            "coicop_code": "01.1.1.1.1",
            "canonical_name": "Phka Rumduol Jasmine Rice 5kg",
            "price_ratio": 1.10,
            "primary_store": "aeon",
            "observation_count": 5
        },
        {
            "item_id": "rice-j2",
            "coicop_division": "01",
            "coicop_code": "01.1.1.1.1",
            "canonical_name": "Jasmine Rice 10kg",
            "price_ratio": 1.10,
            "primary_store": "delishop",
            "observation_count": 5
        },
        # White Rice (Store A)
        {
            "item_id": "rice-w1",
            "coicop_division": "01",
            "coicop_code": "01.1.1.1.2",
            "canonical_name": "Mixed White Rice 5kg",
            "price_ratio": 1.05,
            "primary_store": "aeon",
            "observation_count": 5
        },
        # Bread (Store A)
        {
            "item_id": "bread-1",
            "coicop_division": "01",
            "coicop_code": "01.1.1.2",
            "canonical_name": "French Baguette",
            "price_ratio": 1.00,
            "primary_store": "aeon",
            "observation_count": 5
        },
        # Oils & Fats (Case B: no subclasses, Class is the EA)
        {
            "item_id": "oil-1",
            "coicop_division": "01",
            "coicop_code": "01.1.5",
            "canonical_name": "Vegetable Cooking Oil 1L",
            "price_ratio": 1.20,
            "primary_store": "aeon",
            "observation_count": 5
        },
        {
            "item_id": "oil-2",
            "coicop_division": "01",
            "coicop_code": "01.1.5",
            "canonical_name": "Soybean Cooking Oil 2L",
            "price_ratio": 1.20,
            "primary_store": "delishop",
            "observation_count": 5
        }
    ])
    
    df_div, headline = cpi_engine.aggregate_division_and_headline(items, calc_date)
    
    # 1. Verify Case A: Class 01.1.1
    # Available subclasses:
    # 01.1.1.1.1 (wt=3.052, idx=110.0)
    # 01.1.1.1.2 (wt=2.681, idx=105.0)
    # 01.1.1.2 (wt=0.173, idx=100.0)
    # Total available weight = 3.052 + 2.681 + 0.173 = 5.906
    expected_cls_0111 = (3.052 * 110.0 + 2.681 * 105.0 + 0.173 * 100.0) / 5.906
    # Note: Rice parent (6.162) is NOT in denominator, avoiding double-counting!
    
    # 2. Verify Case B: Class 01.1.5
    expected_cls_0115 = 120.0
    
    # 3. Verify Group 01.1 (Food)
    # Classes available in 01.1 are:
    # 01.1.1 (official class weight = 8.274)
    # 01.1.5 (official class weight = 0.920)
    # Sum of available class weights = 8.274 + 0.920 = 9.194
    expected_grp_011 = (8.274 * expected_cls_0111 + 0.920 * expected_cls_0115) / 9.194
    
    # 4. Verify Division 01:
    # Only Group 01.1 is active, so Division 01 index equals Group 01.1 index:
    div01_row = df_div[df_div["coicop_division"] == "01"].iloc[0]
    assert div01_row["division_index"] == pytest.approx(expected_grp_011, abs=0.05)
    
    # 5. Coverage weight:
    # EAs active: 01.1.1.1.1 (3.052) + 01.1.1.1.2 (2.681) + 01.1.1.2 (0.173) + 01.1.5 (0.920) = 6.826%
    assert pytest.approx(headline["ea_coverage_weight"], 0.01) == 6.826
    assert pytest.approx(headline["coverage_weight"], 0.01) == 44.78
    assert headline["active_elementary_aggregate_count"] == 4

def test_missing_elementary_aggregates_weight_renormalization(cpi_engine):
    """
    Ensures missing EAs:
    - Are NOT assigned an artificial index of 100.0.
    - Are excluded from numerator and denominator.
    - Weights of available EAs are properly renormalized to 100%.
    """
    calc_date = date(2026, 9, 27)
    
    # Class 07.2.2 (Fuels) has 3 subclasses:
    # 07.2.2.1 Gasoline (4.969%)
    # 07.2.2.2 Diesel (0.144%)
    # 07.2.2.3 Motor Oil (0.062%)
    # If only Gasoline is observed at +10% (110.0), Class 07.2.2 index should be exactly 110.0!
    # (NOT dragged down toward 100 by missing diesel and motor oil).
    items = pd.DataFrame([
        {
            "item_id": "fuel-gas-1",
            "coicop_division": "07",
            "coicop_code": "07.2.2.1",
            "canonical_name": "Gasoline Super 95",
            "price_ratio": 1.10,
            "primary_store": "tela",
            "observation_count": 10
        }
    ])
    
    df_div, headline = cpi_engine.aggregate_division_and_headline(items, calc_date)
    div07 = df_div[df_div["coicop_division"] == "07"].iloc[0]
    
    # Division 07 index must be exactly 110.0
    assert div07["division_index"] == pytest.approx(110.0, abs=0.01)
    # Active EA count must be 1
    assert headline["active_elementary_aggregate_count"] == 1
    # Coverage weight: EA level is Gasoline (4.969%), division level is Transport (12.228%)
    assert pytest.approx(headline["ea_coverage_weight"], 0.001) == 4.969
    assert pytest.approx(headline["coverage_weight"], 0.001) == 12.228


def test_geometric_subclass_aggregation(cpi_engine):
    """
    Verifies that when use_geometric_subclass=True, subclasses combine
    via an equal-weighted geometric mean (Jevons-of-Jevons):
    I_class = exp((1/K) * sum(ln(I_e))).
    """
    ea_indices = {
        "01.1.1.1.1": 110.0,
        "01.1.1.1.2": 90.0,
        "01.1.1.2": 100.0,
    }
    class_indices, _, _ = cpi_engine.hierarchy.aggregate_multi_tier(
        ea_indices, use_geometric_subclass=True
    )
    expected_geom = float(np.exp((np.log(110.0) + np.log(90.0) + np.log(100.0)) / 3))
    assert pytest.approx(class_indices["01.1.1"], 0.001) == expected_geom


def test_store_weighted_jevons(cpi_engine):
    """
    Verifies that store_weights parameter weights store geometric means
    by their turnover market shares:
    I_EA = exp(sum(theta_s * ln(I_s))).
    """
    calc_date = date(2026, 9, 27)
    items = pd.DataFrame([
        # Store A: 10% inflation
        {"item_id": "item-a", "coicop_division": "01", "coicop_code": "01.1.5",
         "price_ratio": 1.10, "primary_store": "aeon", "observation_count": 100},
        # Store B: 0% inflation
        {"item_id": "item-b", "coicop_division": "01", "coicop_code": "01.1.5",
         "price_ratio": 1.00, "primary_store": "lucky", "observation_count": 5},
    ])
    # Case 1: Equal store weights (default) -> sqrt(1.10 * 1.00) * 100 = 104.88
    _, headline_eq = cpi_engine.aggregate_division_and_headline(items, calc_date)
    expected_eq = float(np.exp((np.log(1.10) + np.log(1.00)) / 2) * 100.0)
    assert pytest.approx(headline_eq["headline_cpi"], 0.01) == expected_eq

    # Case 2: Store A has 80% market share, Store B has 20%
    store_wts = {"aeon": 0.80, "lucky": 0.20}
    _, headline_wt = cpi_engine.aggregate_division_and_headline(items, calc_date, store_weights=store_wts)
    expected_wt = float(np.exp(0.80 * np.log(1.10) + 0.20 * np.log(1.00)) * 100.0)
    assert pytest.approx(headline_wt["headline_cpi"], 0.01) == expected_wt

