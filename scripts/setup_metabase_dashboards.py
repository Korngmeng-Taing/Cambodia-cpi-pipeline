"""
=============================================================================
CAMBODIA CPI PIPELINE — METABASE OPERATIONS & MONITORING PROVISIONER
Provisions the dedicated Pipeline Operations, Store Ingestion Monitoring,
and Dimension/Fact Explorer Dashboard directly into Metabase (PostgreSQL 5432).
=============================================================================
"""

import psycopg2
import json
import secrets
import string
from datetime import datetime, timezone

def generate_entity_id(length=21):
    alphabet = string.ascii_letters + string.digits + "-_"
    return "".join(secrets.choice(alphabet) for _ in range(length))

def get_or_create_collection(cur, name, description, color="#509EE3"):
    cur.execute("SELECT id FROM collection WHERE name = %s AND archived = false", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    
    slug = name.lower().replace(" ", "-").replace("/", "-")
    entity_id = generate_entity_id()
    now = datetime.now(timezone.utc)
    cur.execute("""
        INSERT INTO collection (name, description, slug, entity_id, location, archived, personal_owner_id, namespace, created_at, type)
        VALUES (%s, %s, %s, %s, '/', false, NULL, NULL, %s, 'default')
        RETURNING id;
    """, (name, description, slug, entity_id, now))
    return cur.fetchone()[0]

def create_or_update_card(cur, name, description, display, query_sql, viz_settings, collection_id, db_id=2, creator_id=1):
    dataset_query = {
        "database": db_id,
        "type": "native",
        "native": {
            "query": query_sql.strip(),
            "template-tags": {}
        }
    }
    now = datetime.now(timezone.utc)
    
    cur.execute("SELECT id FROM report_card WHERE name = %s AND collection_id = %s AND archived = false", (name, collection_id))
    row = cur.fetchone()
    if row:
        card_id = row[0]
        cur.execute("""
            UPDATE report_card 
            SET description = %s, display = %s, dataset_query = %s, visualization_settings = %s, updated_at = %s
            WHERE id = %s;
        """, (description, display, json.dumps(dataset_query), json.dumps(viz_settings), now, card_id))
        return card_id
    else:
        entity_id = generate_entity_id()
        cur.execute("""
            INSERT INTO report_card (
                created_at, updated_at, name, description, display, dataset_query,
                visualization_settings, creator_id, database_id, query_type, archived,
                collection_id, enable_embedding, dataset, entity_id, collection_preview, type
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'native', false, %s, false, false, %s, true, 'question')
            RETURNING id;
        """, (now, now, name, description, display, json.dumps(dataset_query), json.dumps(viz_settings), creator_id, db_id, collection_id, entity_id))
        return cur.fetchone()[0]

def create_or_update_dashboard(cur, name, description, collection_id, creator_id=1):
    now = datetime.now(timezone.utc)
    cur.execute("SELECT id FROM report_dashboard WHERE name = %s AND collection_id = %s AND archived = false", (name, collection_id))
    row = cur.fetchone()
    if row:
        dash_id = row[0]
        cur.execute("""
            UPDATE report_dashboard
            SET description = %s, updated_at = %s, width = 'fixed', auto_apply_filters = true
            WHERE id = %s;
        """, (description, now, dash_id))
        return dash_id
    else:
        entity_id = generate_entity_id()
        cur.execute("""
            INSERT INTO report_dashboard (
                created_at, updated_at, name, description, creator_id, parameters,
                show_in_getting_started, enable_embedding, archived, collection_id,
                entity_id, auto_apply_filters, width
            )
            VALUES (%s, %s, %s, %s, %s, '[]', false, false, false, %s, %s, true, 'fixed')
            RETURNING id;
        """, (now, now, name, description, creator_id, collection_id, entity_id))
        return cur.fetchone()[0]

def place_card_on_dashboard(cur, dashboard_id, card_id, col, row, size_x, size_y, viz_settings=None):
    now = datetime.now(timezone.utc)
    viz_json = json.dumps(viz_settings if viz_settings is not None else {})
    
    cur.execute("""
        SELECT id FROM report_dashboardcard 
        WHERE dashboard_id = %s AND card_id = %s;
    """, (dashboard_id, card_id))
    existing = cur.fetchone()
    
    if existing:
        cur.execute("""
            UPDATE report_dashboardcard
            SET col = %s, row = %s, size_x = %s, size_y = %s, updated_at = %s, visualization_settings = %s
            WHERE id = %s;
        """, (col, row, size_x, size_y, now, viz_json, existing[0]))
    else:
        entity_id = generate_entity_id()
        cur.execute("""
            INSERT INTO report_dashboardcard (
                created_at, updated_at, size_x, size_y, row, col, card_id,
                dashboard_id, parameter_mappings, visualization_settings, entity_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '[]', %s, %s);
        """, (now, now, size_x, size_y, row, col, card_id, dashboard_id, viz_json, entity_id))

def purge_other_items(cur, target_collection_name, target_dashboard_name):
    print("[0/2] Purging other legacy dashboards, cards, collections, and dropped tables from Metabase...")
    # 1. Remove old dashboard card placements
    cur.execute("""
        DELETE FROM report_dashboardcard 
        WHERE dashboard_id IN (
            SELECT id FROM report_dashboard 
            WHERE name != %s
        );
    """, (target_dashboard_name,))
    
    # 2. Remove old dashboards
    cur.execute("""
        DELETE FROM report_dashboard 
        WHERE name != %s;
    """, (target_dashboard_name,))
    
    # 3. Remove old cards not in target collection
    cur.execute("""
        DELETE FROM report_card 
        WHERE collection_id IN (
            SELECT id FROM collection 
            WHERE name != %s AND personal_owner_id IS NULL
        );
    """, (target_collection_name,))
    
    # 4. Remove other non-personal collections
    cur.execute("""
        DELETE FROM collection 
        WHERE name != %s AND personal_owner_id IS NULL;
    """, (target_collection_name,))

    # 5. Purge dropped tables from Metabase internal schema cache
    cpi_conn = psycopg2.connect("postgresql://cpi_user:cpi_pass@localhost:5432/cpi_db")
    cpi_cur = cpi_conn.cursor()
    cpi_cur.execute("""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema IN ('silver', 'gold', 'staging');
    """)
    real_tables = set(cpi_cur.fetchall())
    cpi_conn.close()

    cur.execute("SELECT id, schema, name, active FROM metabase_table;")
    all_mb_tables = cur.fetchall()
    for tid, tschema, tname, active in all_mb_tables:
        if (tschema, tname) not in real_tables or active is False:
            cur.execute("DELETE FROM metabase_fieldvalues WHERE field_id IN (SELECT id FROM metabase_field WHERE table_id = %s);", (tid,))
            cur.execute("DELETE FROM metabase_field WHERE table_id = %s;", (tid,))
            cur.execute("DELETE FROM metabase_table WHERE id = %s;", (tid,))

    # Set visibility
    cur.execute("UPDATE metabase_table SET visibility_type = NULL WHERE schema = 'silver' AND name IN ('dim_stores', 'dim_items', 'fct_daily_prices');")
    hidden_silver = [
        'canonical_items', 'classification_ground_truth', 'classification_queue',
        'coicop_category_map', 'coicop_classification_seed', 'coicop_keywords',
        'coicop_override', 'coicop_override_manual', 'coicop_store_defaults',
        'coicop_text_rules', 'dim_coicop_ai_cache', 'item_match_log',
        'needs_review', 'utility_tariffs', 'fct_daily_prices_imputed'
    ]
    for t in hidden_silver:
        cur.execute("UPDATE metabase_table SET visibility_type = 'hidden' WHERE schema = 'silver' AND name = %s;", (t,))

def provision_all():
    conn = psycopg2.connect("postgresql://metabase:metabase@localhost:5432/metabase")
    cur = conn.cursor()
    
    col_name = "01 - Cambodia CPI Pipeline Monitoring & Data Explorer"
    dash_name = "Cambodia CPI Pipeline Operations & Monitoring Dashboard"
    
    purge_other_items(cur, col_name, dash_name)
    
    print("[1/2] Setting up Collection in Metabase...")
    c_ops = get_or_create_collection(
        cur, 
        col_name, 
        "Source health, DAG ingest status, store comparisons, fuel prices, and dimensional tables", 
        "#2E5BFF"
    )

    print("[2/2] Building Dedicated Operations & Data Monitoring Dashboard...")
    d_id = create_or_update_dashboard(
        cur, 
        dash_name, 
        "Live monitoring of scraper sources, daily ingestion volumes, store comparisons, fuel prices, and Silver dim/fact tables.", 
        c_ops
    )

    cards = [
        # --- TOP KPI ROW ---
        {
            "name": "Total Sources Monitored",
            "desc": "Total configured scraper sources and retail market channels.",
            "display": "scalar",
            "sql": "SELECT COUNT(*) AS \"Total Sources\" FROM silver.dim_stores;",
            "viz": {},
            "grid": (0, 0, 4, 3)
        },
        {
            "name": "Failed / Missing Ingestions Today",
            "desc": "Number of configured sources that failed or returned 0 quotes today.",
            "display": "scalar",
            "sql": """
                SELECT GREATEST(0, 
                    (SELECT COUNT(*) FROM silver.dim_stores WHERE is_active = TRUE) - 
                    (SELECT COUNT(DISTINCT store_slug) FROM silver.fct_daily_prices WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.fct_daily_prices))
                ) AS \"Failed / Missing Ingestions Today\";
            """,
            "viz": {},
            "grid": (4, 0, 5, 3)
        },
        {
            "name": "Total Products Ingested Today",
            "desc": "Total cleaned product quotes collected across all stores today.",
            "display": "scalar",
            "sql": "SELECT COUNT(*) AS \"Total Ingested Products\" FROM silver.fct_daily_prices WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.fct_daily_prices);",
            "viz": {},
            "grid": (9, 0, 5, 3)
        },
        {
            "name": "Unique Canonical Products Today",
            "desc": "Total distinct canonical product items tracked today.",
            "display": "scalar",
            "sql": "SELECT COUNT(DISTINCT item_id) AS \"Unique Products Today\" FROM silver.fct_daily_prices WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.fct_daily_prices);",
            "viz": {},
            "grid": (14, 0, 5, 3)
        },
        {
            "name": "Official MEF USD/KHR Rate Today",
            "desc": "Official daily exchange rate from Ministry of Economy and Finance (MEF API).",
            "display": "scalar",
            "sql": "SELECT rate AS \"USD/KHR Rate Today\" FROM staging.exchange_rates WHERE execution_date = (SELECT MAX(execution_date) FROM staging.exchange_rates);",
            "viz": {},
            "grid": (19, 0, 5, 3)
        },

        # --- STORE INGESTION & COMPARISONS ---
        {
            "name": "Total Ingested Products Per Store Today",
            "desc": "Cleaned product quote volume collected per store channel today.",
            "display": "bar",
            "sql": """
                SELECT 
                    store_slug AS "Store",
                    COUNT(*) AS "Products Ingested"
                FROM silver.fct_daily_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.fct_daily_prices)
                GROUP BY store_slug
                ORDER BY "Products Ingested" DESC;
            """,
            "viz": {
                "graph.dimensions": ["Store"],
                "graph.metrics": ["Products Ingested"],
                "graph.colors": ["#2E5BFF"]
            },
            "grid": (0, 3, 11, 8)
        },
        {
            "name": "Store Ingest Volume: Today vs Yesterday",
            "desc": "Comparison of ingested product count per store between today and yesterday.",
            "display": "table",
            "sql": """
                WITH today_stats AS (
                    SELECT store_slug, COUNT(*) AS count_today
                    FROM silver.fct_daily_prices
                    WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.fct_daily_prices)
                    GROUP BY store_slug
                ),
                yesterday_stats AS (
                    SELECT store_slug, COUNT(*) AS count_yesterday
                    FROM silver.fct_daily_prices
                    WHERE scrape_date = (SELECT MAX(scrape_date) - INTERVAL '1 day' FROM silver.fct_daily_prices)
                    GROUP BY store_slug
                )
                SELECT 
                    s.store_slug AS "Store Slug",
                    s.store_name AS "Store Name",
                    COALESCE(t.count_today, 0) AS "Today Ingest",
                    COALESCE(y.count_yesterday, 0) AS "Yesterday Ingest",
                    COALESCE(t.count_today, 0) - COALESCE(y.count_yesterday, 0) AS "Volume Diff",
                    ROUND((COALESCE(t.count_today, 0) - COALESCE(y.count_yesterday, 0))::NUMERIC / NULLIF(y.count_yesterday, 0) * 100.0, 1) AS "DoD Change (%)"
                FROM silver.dim_stores s
                LEFT JOIN today_stats t ON t.store_slug = s.store_slug
                LEFT JOIN yesterday_stats y ON y.store_slug = s.store_slug
                ORDER BY "Today Ingest" DESC;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (11, 3, 13, 8)
        },

        # --- LIVE FUEL & GASOLINE PRICES ---
        {
            "name": "All Gasoline & Retail Fuel Prices Today",
            "desc": "Live prices of Gasoline (EA92, EA95), Diesel, and Petroleum products collected today.",
            "display": "table",
            "sql": """
                SELECT 
                    name_clean AS "Fuel Product Name",
                    store_slug AS "Provider / Outlet",
                    price_khr AS "Price (KHR)",
                    unit_price_khr AS "Unit Price (KHR/L)",
                    currency AS "Currency",
                    scrape_date AS "Date"
                FROM silver.fct_daily_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.fct_daily_prices)
                  AND (
                      store_slug IN ('moc_fuel', 'new_gasoline', 'total_energies', 'tela', 'caltex', 'ptt')
                      OR name_clean ILIKE '%gasoline%'
                      OR name_clean ILIKE '%ea92%'
                      OR name_clean ILIKE '%ea95%'
                      OR (name_clean ILIKE '%diesel%' AND name_clean NOT ILIKE '%edt%' AND name_clean NOT ILIKE '%edp%' AND name_clean NOT ILIKE '%spray%')
                  )
                ORDER BY price_khr ASC;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 11, 24, 6)
        },

        # --- CORE DIMENSION & FACT TABLES ---
        {
            "name": "Table: dim_store",
            "desc": "Master store metadata table including store slugs, names, types, currencies, and active status.",
            "display": "table",
            "sql": """
                SELECT 
                    store_slug AS "Store Slug",
                    store_name AS "Store Name",
                    source_type AS "Source Type",
                    channel AS "Channel",
                    default_currency AS "Default Currency",
                    default_coicop_division AS "Default Division",
                    is_active AS "Is Active",
                    total_observations AS "Total Observations",
                    distinct_products_count AS "Tracked Products",
                    last_scraped_at AS "Last Scraped Date"
                FROM silver.dim_stores
                ORDER BY store_slug ASC;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 17, 24, 6)
        },
        {
            "name": "Table: dim_product (silver.dim_items)",
            "desc": "Master product catalog including canonical product UUIDs, names, brands, COICOP codes, and sizes.",
            "display": "table",
            "sql": """
                SELECT 
                    item_id AS "Item ID",
                    canonical_name AS "Canonical Product Name",
                    brand AS "Brand",
                    coicop_code AS "COICOP Code",
                    coicop_division AS "COICOP Division",
                    size_norm AS "Size / Package",
                    unit_of_measure AS "Base Unit",
                    barcode AS "Barcode / EAN",
                    store_count AS "Stores Offering Item",
                    avg_match_confidence AS "Match Confidence"
                FROM silver.dim_items
                ORDER BY canonical_name ASC
                LIMIT 500;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 23, 24, 8)
        },
        {
            "name": "Table: fact_daily_price (silver.fct_daily_prices)",
            "desc": "Atomic fact table containing daily cleaned price quotes, unit prices, promotions, and outlier flags.",
            "display": "table",
            "sql": """
                SELECT 
                    scrape_date AS "Scrape Date",
                    item_id AS "Item ID",
                    name_clean AS "Product Title",
                    store_slug AS "Store",
                    price_khr AS "Price (KHR)",
                    unit_price_khr AS "Unit Price (KHR)",
                    coicop_division AS "COICOP Division",
                    on_promo AS "On Promo",
                    cpi_eligible AS "CPI Eligible",
                    is_outlier AS "Is Outlier"
                FROM silver.fct_daily_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.fct_daily_prices)
                ORDER BY price_khr DESC
                LIMIT 500;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 31, 24, 9)
        }
    ]

    for item in cards:
        cid = create_or_update_card(cur, item["name"], item["desc"], item["display"], item["sql"], item["viz"], c_ops)
        col, row, sx, sy = item["grid"]
        place_card_on_dashboard(cur, d_id, cid, col, row, sx, sy, item["viz"])

    conn.commit()
    conn.close()
    print("\n=============================================================================")
    print("SUCCESS: Metabase Operations & Monitoring Dashboard successfully configured!")
    print(f"  Dashboard ID: {d_id} | Collection ID: {c_ops}")
    print("  Metabase URL: http://localhost:3000")
    print("=============================================================================")

if __name__ == "__main__":
    provision_all()
