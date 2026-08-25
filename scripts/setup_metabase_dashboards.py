"""
=============================================================================
CAMBODIA CPI PIPELINE — METABASE OPERATIONS & MONITORING PROVISIONER
Provisions the dedicated Pipeline Operations, Real-Time DAG Monitoring,
Store Ingestion Tracking, and Dimension/Fact Explorer directly into Metabase.
=============================================================================
"""

import os
import psycopg2
import json
import secrets
import string
from datetime import datetime, timezone

def get_db_connection(dbname):
    hosts = [os.environ.get("POSTGRES_HOST", "localhost"), "postgres", "localhost", "127.0.0.1"]
    for h in hosts:
        try:
            user = "metabase" if dbname == "metabase" else "cpi_user"
            password = "metabase" if dbname == "metabase" else "cpi_pass"
            conn = psycopg2.connect(
                host=h,
                port=5432,
                dbname=dbname,
                user=user,
                password=password,
                connect_timeout=3
            )
            return conn
        except Exception:
            continue
    raise RuntimeError(f"Could not connect to database {dbname} on any candidate host: {hosts}")

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
    print("[0/2] Purging legacy items from Metabase...")
    cur.execute("""
        DELETE FROM report_dashboardcard 
        WHERE dashboard_id IN (
            SELECT id FROM report_dashboard 
            WHERE name != %s
        );
    """, (target_dashboard_name,))
    
    cur.execute("""
        DELETE FROM report_dashboard 
        WHERE name != %s;
    """, (target_dashboard_name,))
    
    cur.execute("""
        DELETE FROM report_card 
        WHERE collection_id IN (
            SELECT id FROM collection 
            WHERE name != %s AND personal_owner_id IS NULL
        );
    """, (target_collection_name,))
    
    cur.execute("""
        DELETE FROM collection 
        WHERE name != %s AND personal_owner_id IS NULL;
    """, (target_collection_name,))

    try:
        cpi_conn = get_db_connection("cpi_db")
        cpi_cur = cpi_conn.cursor()
        cpi_cur.execute("""
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema IN ('silver', 'gold', 'staging', 'airflow_monitor');
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
    except Exception as e:
        print(f"Warning syncing schema tables: {e}")

def provision_all():
    conn = get_db_connection("metabase")
    cur = conn.cursor()
    
    col_name = "01 - Cambodia CPI Pipeline Monitoring & Data Explorer"
    dash_name = "Cambodia CPI Pipeline Operations & Monitoring Dashboard"
    
    purge_other_items(cur, col_name, dash_name)
    
    print("[1/2] Setting up Collection in Metabase...")
    c_ops = get_or_create_collection(
        cur, 
        col_name, 
        "Live DAG monitoring, incident tracking, source ingestion health, fuel prices, and dimensional fact tables", 
        "#2E5BFF"
    )

    print("[2/2] Building Dedicated Operations & Data Monitoring Dashboard...")
    d_id = create_or_update_dashboard(
        cur, 
        dash_name, 
        "Live real-time monitoring of Airflow DAG runs, scraper ingestion progress, failure alerts, and Silver/Gold data warehouse tables.", 
        c_ops
    )

    # Clean out any old cards and placements from this dashboard and collection to eliminate duplicates
    cur.execute("DELETE FROM report_dashboardcard WHERE dashboard_id = %s;", (d_id,))
    cur.execute("DELETE FROM report_card WHERE collection_id = %s;", (c_ops,))

    cards = [
        # ─── ROW 0: TOP KPI STATUS SUMMARY (Y=0, H=3) ──────────────────────────
        {
            "name": "DAGs Running In-Flight Now",
            "desc": "Count of Airflow DAGs currently actively executing right now.",
            "display": "scalar",
            "sql": """
                SELECT COUNT(*) AS "DAGs Running Now"
                FROM airflow_monitor.dag_run
                WHERE state = 'running'
                  AND DATE(start_date AT TIME ZONE 'Asia/Phnom_Penh') = CURRENT_DATE;
            """,
            "viz": {},
            "grid": (0, 0, 4, 3)
        },
        {
            "name": "Failed DAGs / Tasks Today",
            "desc": "Count of DAG runs or task instances that encountered failures today.",
            "display": "scalar",
            "sql": """
                SELECT COUNT(*) AS "Failed Tasks Today"
                FROM airflow_monitor.task_instance
                WHERE state IN ('failed', 'upstream_failed')
                  AND DATE(start_date AT TIME ZONE 'Asia/Phnom_Penh') = CURRENT_DATE;
            """,
            "viz": {},
            "grid": (4, 0, 5, 3)
        },
        {
            "name": "Total Raw Scrapes Today",
            "desc": "Total raw record batches successfully staged in staging.raw_scrapes today.",
            "display": "scalar",
            "sql": """
                SELECT COALESCE(SUM(record_count), 0) AS "Raw Records Staged Today"
                FROM staging.raw_scrapes
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM staging.raw_scrapes);
            """,
            "viz": {},
            "grid": (9, 0, 5, 3)
        },
        {
            "name": "Cleaned Products in Silver (Latest)",
            "desc": "Total cleaned and validated product price quotes in silver.fct_daily_prices.",
            "display": "scalar",
            "sql": """
                SELECT COUNT(*) AS "Cleaned Products in Silver"
                FROM silver.fct_daily_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.fct_daily_prices);
            """,
            "viz": {},
            "grid": (14, 0, 5, 3)
        },
        {
            "name": "Official MEF USD/KHR Rate Today",
            "desc": "Official daily exchange rate from Ministry of Economy and Finance (MEF API).",
            "display": "scalar",
            "sql": """
                SELECT rate AS "USD/KHR Rate Today"
                FROM staging.exchange_rates
                WHERE execution_date = (SELECT MAX(execution_date) FROM staging.exchange_rates);
            """,
            "viz": {},
            "grid": (19, 0, 5, 3)
        },

        # ─── ROW 3: LIVE DAG STATUS & FAILURE ALERT (Y=3, H=7) ─────────────────
        {
            "name": "Failed DAG Tasks & Ingestion Alerts (Today)",
            "desc": "Real-time list of failed DAG tasks and errors. If empty, all tasks ran successfully.",
            "display": "table",
            "sql": """
                SELECT 
                    ti.dag_id AS "Failed DAG",
                    ti.task_id AS "Failed Task",
                    ti.state AS "State",
                    ti.try_number AS "Attempt #",
                    TO_CHAR(ti.start_date AT TIME ZONE 'Asia/Phnom_Penh', 'HH24:MI:SS') AS "Started (ICT)",
                    TO_CHAR(ti.end_date AT TIME ZONE 'Asia/Phnom_Penh', 'HH24:MI:SS') AS "Ended (ICT)",
                    ROUND(ti.duration::numeric, 1) AS "Duration (s)"
                FROM airflow_monitor.task_instance ti
                WHERE DATE(ti.start_date AT TIME ZONE 'Asia/Phnom_Penh') = CURRENT_DATE
                  AND ti.state IN ('failed', 'upstream_failed')
                ORDER BY ti.end_date DESC;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 3, 11, 7)
        },
        {
            "name": "Real-Time Airflow DAG Pipeline Monitor (Today)",
            "desc": "Live execution state of all DAGs triggered today (Scrapers, Silver, Master, Gold).",
            "display": "table",
            "sql": """
                SELECT 
                    dr.dag_id AS "DAG Name",
                    CASE 
                        WHEN dr.state = 'success' THEN 'SUCCESS'
                        WHEN dr.state = 'running' THEN 'RUNNING'
                        WHEN dr.state = 'failed' THEN 'FAILED'
                        WHEN dr.state = 'queued' THEN 'QUEUED'
                        ELSE UPPER(dr.state)
                    END AS "Status",
                    dr.run_type AS "Run Type",
                    TO_CHAR(dr.start_date AT TIME ZONE 'Asia/Phnom_Penh', 'HH24:MI:SS') AS "Start (ICT)",
                    TO_CHAR(dr.end_date AT TIME ZONE 'Asia/Phnom_Penh', 'HH24:MI:SS') AS "End (ICT)",
                    ROUND(EXTRACT(EPOCH FROM (COALESCE(dr.end_date, NOW()) - dr.start_date))::numeric, 1) AS "Duration (s)"
                FROM airflow_monitor.dag_run dr
                WHERE DATE(dr.start_date AT TIME ZONE 'Asia/Phnom_Penh') = CURRENT_DATE
                ORDER BY 
                    CASE WHEN dr.state = 'running' THEN 1 WHEN dr.state = 'failed' THEN 2 ELSE 3 END,
                    dr.start_date DESC;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (11, 3, 13, 7)
        },

        # ─── ROW 10: STORE INGESTION PROGRESS & HEALTH (Y=10, H=8) ────────────
        {
            "name": "Daily Store Scraper Ingestion Progress",
            "desc": "Status and volume of raw scraped data collected today per active retail/market channel.",
            "display": "table",
            "sql": """
                WITH today_scrapes AS (
                    SELECT store_slug, record_count, created_at
                    FROM staging.raw_scrapes
                    WHERE scrape_date = (SELECT MAX(scrape_date) FROM staging.raw_scrapes)
                ),
                today_dags AS (
                    SELECT 
                        REPLACE(REPLACE(dag_id, 'scrape_', ''), '_dag', '') AS store_slug,
                        state,
                        start_date AT TIME ZONE 'Asia/Phnom_Penh' AS start_time,
                        end_date AT TIME ZONE 'Asia/Phnom_Penh' AS end_time
                    FROM airflow_monitor.dag_run
                    WHERE DATE(start_date AT TIME ZONE 'Asia/Phnom_Penh') = CURRENT_DATE
                      AND dag_id LIKE 'scrape_%_dag'
                )
                SELECT 
                    s.store_slug AS "Store Slug",
                    s.store_name AS "Store Name",
                    s.source_type AS "Channel Type",
                    COALESCE(UPPER(d.state), 'NOT RUN') AS "DAG State",
                    COALESCE(ts.record_count, 0) AS "Raw Records Today",
                    CASE 
                        WHEN COALESCE(ts.record_count, 0) > 0 THEN 'INGESTED'
                        WHEN d.state = 'running' THEN 'SCRAPING NOW'
                        WHEN d.state = 'failed' THEN 'FAILED'
                        ELSE 'WAITING'
                    END AS "Ingest Status",
                    TO_CHAR(d.start_time, 'HH24:MI:SS') AS "Started (ICT)",
                    TO_CHAR(d.end_time, 'HH24:MI:SS') AS "Finished (ICT)"
                FROM silver.dim_stores s
                LEFT JOIN today_dags d ON d.store_slug = s.store_slug
                LEFT JOIN today_scrapes ts ON ts.store_slug = s.store_slug
                WHERE s.is_active = TRUE
                ORDER BY 
                    CASE 
                        WHEN COALESCE(ts.record_count, 0) = 0 AND d.state = 'failed' THEN 1
                        WHEN d.state = 'running' THEN 2
                        WHEN COALESCE(ts.record_count, 0) > 0 THEN 3
                        ELSE 4
                    END,
                    "Raw Records Today" DESC;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 10, 12, 8)
        },
        {
            "name": "Store Ingest Volume: Latest Day vs Previous Day",
            "desc": "Comparison of ingested product count per store between latest day and previous day.",
            "display": "table",
            "sql": """
                WITH latest_date AS (
                    SELECT MAX(scrape_date) AS m_date FROM silver.fct_daily_prices
                ),
                today_stats AS (
                    SELECT store_slug, COUNT(*) AS count_today
                    FROM silver.fct_daily_prices, latest_date
                    WHERE scrape_date = latest_date.m_date
                    GROUP BY store_slug
                ),
                yesterday_stats AS (
                    SELECT store_slug, COUNT(*) AS count_yesterday
                    FROM silver.fct_daily_prices, latest_date
                    WHERE scrape_date = latest_date.m_date - INTERVAL '1 day'
                    GROUP BY store_slug
                )
                SELECT 
                    s.store_slug AS "Store Slug",
                    s.store_name AS "Store Name",
                    COALESCE(t.count_today, 0) AS "Latest Ingest",
                    COALESCE(y.count_yesterday, 0) AS "Previous Ingest",
                    COALESCE(t.count_today, 0) - COALESCE(y.count_yesterday, 0) AS "Volume Diff",
                    ROUND((COALESCE(t.count_today, 0) - COALESCE(y.count_yesterday, 0))::NUMERIC / NULLIF(y.count_yesterday, 0) * 100.0, 1) AS "DoD Change (%)"
                FROM silver.dim_stores s
                LEFT JOIN today_stats t ON t.store_slug = s.store_slug
                LEFT JOIN yesterday_stats y ON y.store_slug = s.store_slug
                ORDER BY "Latest Ingest" DESC;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (12, 10, 12, 8)
        },

        # ─── ROW 18: RETAIL & GASOLINE PRICES (Y=18, H=6) ─────────────────────
        {
            "name": "All Gasoline & Retail Fuel Prices (Latest)",
            "desc": "Live prices of Gasoline (EA92, EA95), Diesel, and Petroleum products collected.",
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
            "grid": (0, 18, 24, 6)
        },

        # ─── ROW 24: CORE DIMENSION & FACT TABLES (Y=24..48) ───────────────────
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
            "grid": (0, 24, 24, 6)
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
            "grid": (0, 30, 24, 8)
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
            "grid": (0, 38, 24, 9)
        }
    ]

    for item in cards:
        cid = create_or_update_card(cur, item["name"], item["desc"], item["display"], item["sql"], item["viz"], c_ops)
        col, row, sx, sy = item["grid"]
        place_card_on_dashboard(cur, d_id, cid, col, row, sx, sy, item["viz"])

    conn.commit()
    conn.close()
    print("\n=============================================================================")
    print("SUCCESS: Metabase Operations & Real-Time DAG Monitoring Dashboard configured!")
    print(f"  Dashboard ID: {d_id} | Collection ID: {c_ops}")
    print("  Metabase URL: http://localhost:3000")
    print("=============================================================================")

if __name__ == "__main__":
    provision_all()
