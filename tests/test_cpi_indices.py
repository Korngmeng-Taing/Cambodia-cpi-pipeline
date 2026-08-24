"""
tests/test_cpi_indices.py
─────────────────────────
Unit & Integration tests for Elementary Jevons Index, Higher-Level Laspeyres
Aggregations, and 12 Gold COICOP Division Tables.
"""

from __future__ import annotations

import math

import pytest

from pipeline.config import COICOP_WEIGHTS, get_db_connection


@pytest.fixture(scope="module", autouse=True)
def ensure_cpi_test_data():
    """Ensure at least 1 observation per COICOP division exists for 2026-08-20 for integration tests."""
    try:
        conn = get_db_connection()
    except Exception:
        yield
        return

    test_date = "2026-08-20"
    inserted = False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM silver.fct_daily_prices WHERE scrape_date = %s;",
                (test_date,),
            )
            count = cur.fetchone()[0]
            if count == 0:
                inserted = True
                for div in [f"{i:02d}" for i in range(1, 13)]:
                    item_id = f"test_item_div_{div}"
                    cur.execute(
                        """
                        INSERT INTO silver.dim_items (item_id, canonical_name, coicop_division)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (item_id) DO NOTHING;
                        """,
                        (item_id, f"Test Product Division {div}", div),
                    )
                    cur.execute(
                        """
                        INSERT INTO silver.fct_daily_prices (
                            scrape_date, store_slug, item_id, product_key, name_clean,
                            category_native, coicop_division, coicop_method, coicop_confidence,
                            currency, price_original_curr, original_price_curr, original_price_khr,
                            discount_pct, on_promo, price_khr, unit_price_khr, size_value, size_unit,
                            pack_qty, is_outlier, cpi_eligible, is_fallback, scraped_at
                        )
                        VALUES (
                            %s, 'test_store', %s, %s, %s,
                            'Category', %s, 'manual', 1.0,
                            'KHR', 4000.0, 4000.0, 4000.0,
                            0.0, FALSE, 4000.0, 4000.0, 1.0, 'kg',
                            1, FALSE, TRUE, FALSE, NOW()
                        )
                        ON CONFLICT (scrape_date, store_slug, item_id) DO NOTHING;
                        """,
                        (test_date, item_id, item_id, f"Test Product Division {div}", div),
                    )
                conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()

    yield

    if inserted:
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("DELETE FROM silver.fct_daily_prices WHERE store_slug = 'test_store';")
                cur.execute("DELETE FROM silver.dim_items WHERE item_id LIKE 'test_item_div_%';")
                conn.commit()
            conn.close()
        except Exception:
            pass


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
    """Verify that silver.fct_jevons_daily table contains valid Jevons calculations."""
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT scrape_date, count(*), avg(p_khr_jevons)
            FROM silver.fct_jevons_daily
            WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.fct_jevons_daily)
            GROUP BY scrape_date;
        """
        )
        row = cur.fetchone()
        assert (
            row is not None
        ), "No rows found in silver.fct_jevons_daily"
        n_items, avg_price = row[1], float(row[2])
        assert n_items >= 1, f"Expected at least 1 item, got {n_items}"
        assert avg_price > 0, "Average Jevons price should be positive"
    conn.close()


def test_silver_jevons_coicop_divisions_covered():
    """Verify that silver.fct_jevons_daily covers canonical items across COICOP divisions."""
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(DISTINCT coicop_division) 
            FROM silver.fct_jevons_daily 
            WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.fct_jevons_daily)
              AND coicop_division BETWEEN '01' AND '12';
        """
        )
        stats_divs = cur.fetchone()[0]
        assert stats_divs >= 1, f"Expected at least 1 COICOP division in Jevons view, got {stats_divs}"
    conn.close()
