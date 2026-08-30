"""
tests/test_cpi_indices.py
────────────────────────
Tests for the Gold Star Schema (dim_items, dim_stores, fct_daily_prices),
COICOP weight integrity, and Jevons formula math properties.

NOTE: CPI index computation (Jevons aggregation, Laspeyres roll-ups)
Fisher) is planned but NOT implemented yet — these tests only cover the
materialized star schema and reference-data invariants.
"""

from __future__ import annotations

import math

import psycopg2
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
                "SELECT count(*) FROM gold.fct_daily_prices WHERE scrape_date = %s;",
                (test_date,),
            )
            count = cur.fetchone()[0]
            if count == 0:
                inserted = True
                for div in [f"{i:02d}" for i in range(1, 13)]:
                    item_id = f"test_item_div_{div}"
                    cur.execute(
                        """
                        INSERT INTO gold.dim_items (item_id, canonical_name, coicop_division)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (item_id) DO NOTHING;
                        """,
                        (item_id, f"Test Product Division {div}", div),
                    )
                    cur.execute(
                        """
                        INSERT INTO gold.fct_daily_prices (
                            scrape_date, store_slug, item_id, price_khr, original_price_khr,
                            discount_pct, on_promo, unit_price_khr, size_value, size_unit,
                            pack_qty, cpi_eligible, is_outlier, is_fallback
                        )
                        VALUES (
                            %s, 'test_store', %s, 4000.0, 4000.0,
                            0.0, FALSE, 4000.0, 1.0, 'kg',
                            1, TRUE, FALSE, FALSE
                        )
                        ON CONFLICT (scrape_date, store_slug, item_id) DO NOTHING;
                        """,
                        (test_date, item_id),
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
                cur.execute("DELETE FROM gold.fct_daily_prices WHERE store_slug = 'test_store';")
                cur.execute("DELETE FROM gold.dim_items WHERE item_id LIKE 'test_item_div_%';")
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


def test_dutot_and_carli_elementary_indices():
    """Verify Dutot (ratio of arithmetic means) and Carli (arithmetic mean of ratios)."""
    base_prices = [1000.0, 2000.0, 5000.0]
    curr_prices = [1200.0, 2100.0, 5500.0]

    # Dutot: sum(curr) / sum(base) = 8800 / 8000 = 1.10
    dutot = sum(curr_prices) / sum(base_prices)
    assert math.isclose(dutot, 1.10, rel_tol=1e-4)

    # Carli: (1.20 + 1.05 + 1.10) / 3 = 3.35 / 3 = 1.11666...
    relatives = [c / b for c, b in zip(curr_prices, base_prices, strict=True)]
    carli = sum(relatives) / len(relatives)
    assert math.isclose(carli, 1.116666, rel_tol=1e-4)

    # By Jensen's Inequality: Carli >= Jevons >= Harmonic
    log_sum = sum(math.log(r) for r in relatives)
    jevons = math.exp(log_sum / len(relatives))
    assert carli >= jevons


def test_discount_clamping_and_promo_detection():
    """Verify promotional discount clamping invariants (0% to 95% bound)."""
    def compute_discount(orig: float, curr: float) -> tuple[float, bool]:
        if orig <= 0 or curr <= 0 or curr >= orig:
            return 0.0, False
        raw_pct = ((orig - curr) / orig) * 100.0
        # Clamp: discount > 95% is treated as data error/liquidation anomaly
        if raw_pct > 95.0:
            return 0.0, False
        return round(raw_pct, 2), True

    # 20% normal discount
    pct, on_promo = compute_discount(5000.0, 4000.0)
    assert pct == 20.0 and on_promo is True

    # 0% discount (same price)
    pct, on_promo = compute_discount(5000.0, 5000.0)
    assert pct == 0.0 and on_promo is False

    # Negative discount (price increase / surcharge)
    pct, on_promo = compute_discount(5000.0, 6000.0)
    assert pct == 0.0 and on_promo is False

    # Extreme anomaly: $1000 item priced at $1 (99.9% discount -> rejected by clamp)
    pct, on_promo = compute_discount(1000.0, 1.0)
    assert pct == 0.0 and on_promo is False


def test_gold_star_schema_tables():
    """Verify that Gold layer contains dim_items, dim_stores, and fct_daily_prices with essential columns."""
    try:
        conn = get_db_connection()
    except Exception as e:
        pytest.skip(f"Database not available: {e}")

    try:
        with conn.cursor() as cur:
            # 1. Verify gold.dim_stores
            cur.execute("SELECT count(*) FROM gold.dim_stores;")
            store_count = cur.fetchone()[0]
            assert store_count >= 1, f"Expected stores in gold.dim_stores, found {store_count}"

            # 2. Verify gold.dim_items
            cur.execute("SELECT count(*) FROM gold.dim_items;")
            item_count = cur.fetchone()[0]
            assert item_count >= 1, f"Expected items in gold.dim_items, found {item_count}"

            # 3. Verify gold.fct_daily_prices structure
            cur.execute(
                """
                SELECT scrape_date, count(*), avg(price_khr)
                FROM gold.fct_daily_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM gold.fct_daily_prices)
                GROUP BY scrape_date;
                """
            )
            row = cur.fetchone()
            assert row is not None, "No rows found in gold.fct_daily_prices"
            n_quotes, avg_price = row[1], float(row[2])
            assert n_quotes >= 1, f"Expected at least 1 quote, got {n_quotes}"
            assert avg_price > 0, "Average price in gold.fct_daily_prices must be positive"

            # 4. Verify unified silver.clean_store_prices
            cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'silver' AND table_name = 'clean_store_prices';")
            tbl_exists = cur.fetchone()[0]
            assert tbl_exists == 1, "silver.clean_store_prices table must exist"
    finally:
        conn.close()
