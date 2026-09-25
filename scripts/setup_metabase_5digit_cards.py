"""
scripts/setup_metabase_5digit_cards.py
──────────────────────────────────────
Provisions 5-Digit UN COICOP 2018 cards into Metabase for interactive dashboard analysis.
"""
from __future__ import annotations

import json
import logging
import secrets
import string
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("metabase_5digit")

def generate_entity_id(length=21):
    alphabet = string.ascii_letters + string.digits + "-_"
    return "".join(secrets.choice(alphabet) for _ in range(length))

def get_metabase_conn():
    return psycopg2.connect("postgresql://metabase:metabase@localhost:5432/metabase")

def create_card(cur, name, description, display, query_sql, viz_settings, collection_id=1, db_id=2):
    now = datetime.now(timezone.utc)
    cur.execute("SELECT id FROM report_card WHERE name = %s AND archived = false", (name,))
    row = cur.fetchone()
    dataset_query = {
        "database": db_id,
        "type": "native",
        "native": {
            "query": query_sql.strip(),
            "template-tags": {}
        }
    }
    if row:
        card_id = row[0]
        cur.execute("""
            UPDATE report_card 
            SET description = %s, display = %s, dataset_query = %s, visualization_settings = %s, updated_at = %s
            WHERE id = %s;
        """, (description, display, json.dumps(dataset_query), json.dumps(viz_settings), now, card_id))
        log.info(f"Updated card {card_id}: {name}")
        return card_id
    else:
        entity_id = generate_entity_id()
        cur.execute("""
            INSERT INTO report_card (
                created_at, updated_at, name, description, display, dataset_query,
                visualization_settings, creator_id, database_id, query_type, archived,
                collection_id, enable_embedding, dataset, entity_id, collection_preview, type
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, 1, %s, 'native', false, %s, false, false, %s, true, 'question')
            RETURNING id;
        """, (now, now, name, description, display, json.dumps(dataset_query), json.dumps(viz_settings), db_id, collection_id, entity_id))
        card_id = cur.fetchone()[0]
        log.info(f"Created card {card_id}: {name}")
        return card_id

def attach_to_dashboard(cur, dashboard_id, card_id, row, col, size_x, size_y, viz_settings):
    now = datetime.now(timezone.utc)
    cur.execute("SELECT id FROM report_dashboardcard WHERE dashboard_id = %s AND card_id = %s", (dashboard_id, card_id))
    r = cur.fetchone()
    if r:
        cur.execute("""
            UPDATE report_dashboardcard
            SET row = %s, col = %s, size_x = %s, size_y = %s, visualization_settings = %s, updated_at = %s
            WHERE id = %s;
        """, (row, col, size_x, size_y, json.dumps(viz_settings), now, r[0]))
    else:
        entity_id = generate_entity_id()
        cur.execute("""
            INSERT INTO report_dashboardcard (
                created_at, updated_at, dashboard_id, card_id, row, col,
                size_x, size_y, parameter_mappings, visualization_settings, entity_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '[]', %s, %s);
        """, (now, now, dashboard_id, card_id, row, col, size_x, size_y, json.dumps(viz_settings), entity_id))

def main():
    log.info("Connecting to Metabase PostgreSQL backend...")
    conn = get_metabase_conn()
    try:
        with conn.cursor() as cur:
            # Check Macro Dashboard ID
            cur.execute("SELECT id FROM report_dashboard WHERE name LIKE '%Macro CPI%' AND archived = false LIMIT 1;")
            dash_row = cur.fetchone()
            dash_id = dash_row[0] if dash_row else 139
            log.info(f"Targeting Dashboard ID: {dash_id}")

            # Card 1: Rice Inflation Index
            sql_rice = """
                SELECT 
                    calculation_date as "Date",
                    rice_cpi_jevons as "Rice Jevons Index",
                    ROUND(avg_current_price_khr, 0) as "Mean Price (KHR)",
                    distinct_rice_products as "Rice Varieties Monitored"
                FROM gold.v_cpi_rice_daily
                ORDER BY calculation_date;
            """
            viz_rice = {
                "graph.dimensions": ["Date"],
                "graph.metrics": ["Rice Jevons Index"],
                "graph.y_axis.scale": "linear"
            }
            c1 = create_card(cur, "🌾 Daily Rice Inflation Index (COICOP 01.1.1.1)", "Daily Jevons elementary index for rice in Phnom Penh supermarkets", "line", sql_rice, viz_rice)
            attach_to_dashboard(cur, dash_id, c1, row=24, col=0, size_x=12, size_y=7, viz_settings=viz_rice)

            # Card 2: 5-Digit Food Subclass Dynamics
            sql_food = """
                SELECT 
                    calculation_date as "Date",
                    category_name as "Food Subclass",
                    jevons_index as "Jevons Index"
                FROM gold.v_cpi_subclass_5digit_daily
                WHERE coicop_code IN ('01.1.1.1', '01.1.2.1', '01.1.3.1', '01.1.4.3', '01.2.2.2')
                ORDER BY calculation_date;
            """
            viz_food = {
                "graph.dimensions": ["Date", "Food Subclass"],
                "graph.metrics": ["Jevons Index"],
                "graph.y_axis.scale": "linear"
            }
            c2 = create_card(cur, "🥩 5-Digit Food Subclass Dynamics (COICOP 2018)", "Daily elementary price index for Rice, Fresh Pork, Fresh Fish, Dairy, and Soft Drinks", "line", sql_food, viz_food)
            attach_to_dashboard(cur, dash_id, c2, row=24, col=12, size_x=12, size_y=7, viz_settings=viz_food)

            # Card 3: 5-Digit Subclass Explorer Table
            sql_table = """
                SELECT 
                    coicop_code as "COICOP Code",
                    category_name as "Subclass Name",
                    item_count as "Products Monitored",
                    jevons_index as "Jevons Index (Jul=100)",
                    carli_index as "Carli Index",
                    imputed_observations as "Imputed Obs"
                FROM gold.v_cpi_subclass_5digit_daily
                WHERE calculation_date = (SELECT MAX(calculation_date) FROM gold.v_cpi_subclass_5digit_daily)
                ORDER BY item_count DESC
                LIMIT 50;
            """
            viz_table = {}
            c3 = create_card(cur, "📋 UN COICOP 2018 5-Digit Subclass Explorer", "Detailed daily metrics across all 112 subclasses spanning all 12 divisions", "table", sql_table, viz_table)
            attach_to_dashboard(cur, dash_id, c3, row=31, col=0, size_x=24, size_y=9, viz_settings=viz_table)

            conn.commit()
            log.info("🎉 Metabase 5-digit cards successfully provisioned to Dashboard!")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
