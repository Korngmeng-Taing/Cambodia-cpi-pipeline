"""
tests/test_cpi_indices.py
─────────────────────────
Unit & Integration tests for Elementary Jevons Index, Higher-Level Laspeyres
Aggregations, and 12 Gold COICOP Division Tables.
"""

from __future__ import annotations

import math

from pipeline.config import COICOP_WEIGHTS, get_db_connection


def test_coicop_weights_sum_to_100():
    """Verify that the official 12 COICOP division weights sum to exactly 100.000%."""
    total_weight = sum(item["weight"] for item in COICOP_WEIGHTS.values()) * 100.0
    assert math.isclose(
        total_weight, 100.0, rel_tol=1e-5
    ), f"Total weight {total_weight} != 100.0"
    assert (
        len(COICOP_WEIGHTS) == 12
    ), f"Expected 12 divisions, found {len(COICOP_WEIGHTS)}"


def test_jevons_math_properties():
    """Verify mathematical properties of the Jevons elementary formula."""
    # Geometric mean of [1000, 2000, 4000] = (1000 * 2000 * 4000)^(1/3) = 2000
    prices = [1000.0, 2000.0, 4000.0]
    log_sum = sum(math.log(p) for p in prices)
    geom_mean = math.exp(log_sum / len(prices))
    assert math.isclose(geom_mean, 2000.0, rel_tol=1e-4)

    # Ratio of geometric means = Geometric mean of ratios (Jevons axiom)
    base_prices = [1000.0, 2000.0, 4000.0]
    curr_prices = [1100.0, 2200.0, 4400.0]
    relatives = [c / b for c, b in zip(curr_prices, base_prices, strict=False)]
    jevons_rel = math.exp(sum(math.log(r) for r in relatives) / len(relatives))

    geom_base = math.exp(sum(math.log(p) for p in base_prices) / len(base_prices))
    geom_curr = math.exp(sum(math.log(p) for p in curr_prices) / len(curr_prices))
    jevons_ratio = geom_curr / geom_base

    assert math.isclose(jevons_rel, jevons_ratio, rel_tol=1e-5)
    assert math.isclose(jevons_rel, 1.10, rel_tol=1e-5)


def test_silver_fct_jevons_daily_structure():
    """Verify that silver.fct_jevons_daily table/view contains valid Jevons calculations."""
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT scrape_date, count(*), avg(p_khr_jevons), avg(jevons_index_base)
            FROM silver.fct_jevons_daily
            WHERE scrape_date = '2026-08-20'
            GROUP BY scrape_date;
        """
        )
        row = cur.fetchone()
        assert (
            row is not None
        ), "No rows found in silver.fct_jevons_daily for 2026-08-20"
        n_items, avg_price, avg_base_idx = row[1], float(row[2]), float(row[3])
        assert n_items > 10000, f"Expected >10,000 items, got {n_items}"
        assert avg_price > 0, "Average Jevons price should be positive"
        assert (
            10.0 <= avg_base_idx <= 1000.0
        ), f"Base index out of reasonable bounds: {avg_base_idx}"
    conn.close()


def test_silver_fct_laspeyres_daily_divisions():
    """Verify that silver.fct_laspeyres_daily computes indices for all 12 COICOP divisions."""
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT coicop_division, category_index_value, weight_pct
            FROM silver.fct_laspeyres_daily
            WHERE scrape_date = '2026-08-20'
            ORDER BY coicop_division;
        """
        )
        rows = cur.fetchall()
        assert len(rows) == 12, f"Expected 12 COICOP divisions, got {len(rows)}"
        for div, idx_val, w_pct in rows:
            assert (
                float(idx_val) > 0
            ), f"Division {div} has non-positive index value: {idx_val}"
            assert float(w_pct) > 0, f"Division {div} has zero weight"
    conn.close()


def test_gold_12_coicop_views_exist():
    """Verify that all 12 gold COICOP division views are populated."""
    divisions = [
        ("01", "gold.cpi_div01_food"),
        ("02", "gold.cpi_div02_alcohol_tobacco"),
        ("03", "gold.cpi_div03_clothing_footwear"),
        ("04", "gold.cpi_div04_housing_utilities"),
        ("05", "gold.cpi_div05_furnishings"),
        ("06", "gold.cpi_div06_health"),
        ("07", "gold.cpi_div07_transport"),
        ("08", "gold.cpi_div08_communication"),
        ("09", "gold.cpi_div09_recreation"),
        ("10", "gold.cpi_div10_education"),
        ("11", "gold.cpi_div11_restaurants_hotels"),
        ("12", "gold.cpi_div12_misc"),
    ]
    conn = get_db_connection()
    with conn.cursor() as cur:
        for _div_code, view_name in divisions:
            cur.execute(
                f"SELECT count(*) FROM {view_name} WHERE scrape_date = '2026-08-20';"
            )
            count = cur.fetchone()[0]
            assert (
                count > 0
            ), f"Division view {view_name} returned 0 rows for 2026-08-20"
    conn.close()
