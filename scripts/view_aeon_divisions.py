"""
scripts/view_aeon_divisions.py
─────────────────────────────
Query and display AEON product classifications across COICOP divisions.
Usage: python -m scripts.view_aeon_divisions
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.config import get_database_url


def main():
    import psycopg2

    conn_str = get_database_url().replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(conn_str)

    query = """
    WITH aeon_products AS (
        SELECT
            ci.canonical_name,
            ci.brand,
            ci.barcode,
            ci.size_norm,
            COALESCE(cs.coicop_division, 'UNCLASSIFIED') AS coicop_division,
            COALESCE(cs.coicop_code, cs.coicop_division, 'UNCLASSIFIED') AS coicop_code,
            CASE
                WHEN cs.coicop_division = '01' THEN 'Food & Non-Alcoholic Beverages'
                WHEN cs.coicop_division = '02' THEN 'Alcoholic Beverages & Tobacco'
                WHEN cs.coicop_division = '03' THEN 'Clothing & Footwear'
                WHEN cs.coicop_division = '04' THEN 'Housing, Water, Electricity, Gas'
                WHEN cs.coicop_division = '05' THEN 'Furnishings, Household Equipment'
                WHEN cs.coicop_division = '06' THEN 'Health'
                WHEN cs.coicop_division = '07' THEN 'Transport'
                WHEN cs.coicop_division = '08' THEN 'Communication'
                WHEN cs.coicop_division = '09' THEN 'Recreation & Culture'
                WHEN cs.coicop_division = '10' THEN 'Education'
                WHEN cs.coicop_division = '11' THEN 'Restaurants & Hotels'
                WHEN cs.coicop_division = '12' THEN 'Miscellaneous Goods & Services'
                ELSE 'UNCLASSIFIED'
            END AS division_name,
            fdp.store_slug,
            fdp.scrape_date,
            COALESCE(fdp.unit_price_khr, fdp.price_khr) AS unit_price_local
        FROM silver.canonical_items ci
        LEFT JOIN (
            SELECT DISTINCT ON (item_id::text)
                item_id::text AS item_id,
                coicop_division,
                coicop_code
            FROM silver.int_coicop_classified
            ORDER BY item_id::text,
                     CASE WHEN coicop_division <> 'UNCLASSIFIED' THEN 1 ELSE 2 END,
                     coicop_confidence DESC
        ) cs ON cs.item_id = ci.item_id::text
        LEFT JOIN gold.fct_daily_prices fdp ON fdp.item_id = ci.item_id::text
        WHERE fdp.store_slug IN ('aeon', 'aeon3')
          AND fdp.scrape_date = (SELECT MAX(scrape_date) FROM gold.fct_daily_prices WHERE store_slug IN ('aeon', 'aeon3'))
    )
    SELECT
        coicop_division,
        division_name,
        COUNT(DISTINCT canonical_name) AS product_count,
        ROUND(AVG(unit_price_local), 2) AS avg_price,
        MIN(unit_price_local) AS min_price,
        MAX(unit_price_local) AS max_price
    FROM aeon_products
    GROUP BY coicop_division, division_name
    ORDER BY coicop_division;
    """

    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()

        print("=" * 80)
        print("AEON Product Distribution by COICOP Division")
        print("=" * 80)
        print(f"{'Div':<5} {'Division Name':<40} {'Count':>8} {'Avg Price':>12} {'Min':>10} {'Max':>10}")
        print("-" * 80)

        total = 0
        for row in rows:
            div, name, count, avg_price, min_price, max_price = row
            avg_p = f"{avg_price:,.0f}" if avg_price else "N/A"
            min_p = f"{min_price:,.0f}" if min_price else "N/A"
            max_p = f"{max_price:,.0f}" if max_price else "N/A"
            print(f"{div:<5} {name:<40} {count:>8} {avg_p:>12} {min_p:>10} {max_p:>10}")
            total += count

        print("-" * 80)
        print(f"{'TOTAL':<46} {total:>8}")
        print("=" * 80)

        # Show sample products per division
        print("\n" + "=" * 80)
        print("Sample Products per Division")
        print("=" * 80)

        sample_query = """
        WITH aeon_products AS (
            SELECT
                ci.canonical_name,
                ci.brand,
                ci.size_norm,
                COALESCE(cs.coicop_division, 'UNCLASSIFIED') AS coicop_division,
                COALESCE(fdp.unit_price_khr, fdp.price_khr) AS unit_price_local,
                fdp.store_slug
            FROM silver.canonical_items ci
            LEFT JOIN (
                SELECT DISTINCT ON (item_id::text)
                    item_id::text AS item_id,
                    coicop_division
                FROM silver.int_coicop_classified
                ORDER BY item_id::text,
                         CASE WHEN coicop_division <> 'UNCLASSIFIED' THEN 1 ELSE 2 END,
                         coicop_confidence DESC
            ) cs ON cs.item_id = ci.item_id::text
            LEFT JOIN gold.fct_daily_prices fdp ON fdp.item_id = ci.item_id::text
            WHERE fdp.store_slug IN ('aeon', 'aeon3')
              AND fdp.scrape_date = (SELECT MAX(scrape_date) FROM gold.fct_daily_prices WHERE store_slug IN ('aeon', 'aeon3'))
        )
        SELECT coicop_division, canonical_name, brand, size_norm, unit_price_local
        FROM aeon_products
        WHERE coicop_division <> 'UNCLASSIFIED'
        ORDER BY coicop_division, canonical_name
        LIMIT 50;
        """

        cur.execute(sample_query)
        sample_rows = cur.fetchall()

        current_div = None
        for div, name, brand, size, price in sample_rows:
            if div != current_div:
                current_div = div
                div_names = {
                    '01': 'Food', '02': 'Alcohol/Tobacco', '03': 'Clothing',
                    '04': 'Housing', '05': 'Household', '06': 'Health',
                    '07': 'Transport', '08': 'Communication', '09': 'Recreation',
                    '10': 'Education', '11': 'Restaurants/Hotels', '12': 'Personal Care'
                }
                print(f"\n--- Division {div}: {div_names.get(div, 'Unknown')} ---")
            price_str = f"  {price:,.0f}" if price else ""
            print(f"  {name} ({brand or 'N/A'}, {size or 'N/A'}){price_str}")

    conn.close()


if __name__ == "__main__":
    main()
