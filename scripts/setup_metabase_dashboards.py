"""
=============================================================================
CAMBODIA CPI PIPELINE — METABASE PROVISIONER
Provisions:
  1. 🇰🇭 Cambodia Daily Consumer Price Index (CPI) Dashboard
  2. 🚀 Cambodia CPI Pipeline Operations & Monitoring Dashboard
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
            if dbname == "metabase":
                user = os.environ.get("MB_DB_USER", "metabase")
                password = os.environ.get("MB_DB_PASS", "metabase")
            else:
                user = os.environ.get("DB_USER") or os.environ.get("CPI_DB_USER") or "cpi_user"
                password = os.environ.get("DB_PASS") or os.environ.get("CPI_DB_PASSWORD") or "cpi_pass"
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
            SET description = %s, updated_at = %s
            WHERE id = %s;
        """, (description, now, dash_id))
        return dash_id
    else:
        entity_id = generate_entity_id()
        cur.execute("""
            INSERT INTO report_dashboard (
                created_at, updated_at, name, description, creator_id,
                parameters, archived, collection_id, width, enable_embedding,
                entity_id, collection_position, auto_apply_filters
            )
            VALUES (%s, %s, %s, %s, %s, '[]', false, %s, 'fixed', false, %s, 1, true)
            RETURNING id;
        """, (now, now, name, description, creator_id, collection_id, entity_id))
        return cur.fetchone()[0]

def place_card_on_dashboard(cur, dashboard_id, card_id, col, row, size_x, size_y, viz_settings):
    cur.execute("""
        SELECT id FROM report_dashboardcard 
        WHERE dashboard_id = %s AND card_id = %s;
    """, (dashboard_id, card_id))
    r = cur.fetchone()
    now = datetime.now(timezone.utc)
    entity_id = generate_entity_id()
    if r:
        cur.execute("""
            UPDATE report_dashboardcard
            SET col = %s, row = %s, size_x = %s, size_y = %s, visualization_settings = %s, updated_at = %s
            WHERE id = %s;
        """, (col, row, size_x, size_y, json.dumps(viz_settings), now, r[0]))
    else:
        cur.execute("""
            INSERT INTO report_dashboardcard (
                created_at, updated_at, dashboard_id, card_id, row, col,
                size_x, size_y, parameter_mappings, visualization_settings, entity_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '[]', %s, %s);
        """, (now, now, dashboard_id, card_id, row, col, size_x, size_y, json.dumps(viz_settings), entity_id))

def get_metabase_cpi_db_id(cur):
    cur.execute("SELECT id FROM metabase_database WHERE name = 'CPI' OR name = 'cpi_db' ORDER BY id DESC LIMIT 1;")
    row = cur.fetchone()
    if row:
        return row[0]
    return 2

def purge_target_collection_items(cur, col_name, dash_name, db_id=2):
    try:
        cur.execute("SELECT id FROM collection WHERE name = %s;", (col_name,))
        cols = cur.fetchall()
        for c in cols:
            cid = c[0]
            cur.execute("SELECT id FROM report_dashboard WHERE collection_id = %s;", (cid,))
            dashes = cur.fetchall()
            for d in dashes:
                cur.execute("DELETE FROM report_dashboardcard WHERE dashboard_id = %s;", (d[0],))
                cur.execute("DELETE FROM report_dashboard WHERE id = %s;", (d[0],))
            cur.execute("DELETE FROM report_card WHERE collection_id = %s;", (cid,))
    except Exception as e:
        print(f"Notice during purge: {e}")

def provision_all():
    conn = get_db_connection("metabase")
    cur = conn.cursor()
    db_id = get_metabase_cpi_db_id(cur)

    # ═══════════════════════════════════════════════════════════════════════════
    # 1. 🇰🇭 CAMBODIA CPI & INFLATION EXECUTIVE DASHBOARD
    # ═══════════════════════════════════════════════════════════════════════════
    col_name_1 = "01 - Cambodia Daily CPI & Inflation Analytics"
    dash_name_1 = "🇰🇭 Cambodia Daily Consumer Price Index (CPI) Dashboard"
    purge_target_collection_items(cur, col_name_1, dash_name_1, db_id=db_id)

    print("[1/4] Setting up CPI Analytics Collection...")
    c_cpi = get_or_create_collection(
        cur,
        col_name_1,
        "Executive inflation indicators, Jevons micro-indices, 12-division COICOP performance, and price trends.",
        "#008080"
    )

    print("[2/4] Building Executive CPI & Inflation Dashboard...")
    d_cpi_id = create_or_update_dashboard(
        cur,
        dash_name_1,
        "Daily Consumer Price Index (CPI) tracking headline inflation, core inflation, and 12-division COICOP movements across Cambodia.",
        c_cpi
    )

    cpi_cards = [
        # ROW 0: TOP KPI TICKERS (Y=0, H=3)
        {
            "name": "Current Headline Daily CPI (Base 100 = Aug 18, 2026)",
            "desc": "Latest daily headline consumer price index weighted across all 12 UN COICOP divisions.",
            "display": "scalar",
            "sql": """
                SELECT ROUND(headline_cpi::numeric, 2) AS "Headline CPI (Base 100)"
                FROM gold.fct_cpi_daily
                WHERE calculation_date = (SELECT MAX(calculation_date) FROM gold.fct_cpi_daily)
                LIMIT 1;
            """,
            "viz": {},
            "grid": (0, 0, 8, 3)
        },
        {
            "name": "Core CPI (Excluding Food & Energy)",
            "desc": "Underlying inflation measure excluding volatile Food and Transport fuel components.",
            "display": "scalar",
            "sql": """
                SELECT ROUND(core_cpi::numeric, 2) AS "Core CPI (Ex-Food & Energy)"
                FROM gold.fct_cpi_daily
                WHERE calculation_date = (SELECT MAX(calculation_date) FROM gold.fct_cpi_daily)
                LIMIT 1;
            """,
            "viz": {},
            "grid": (8, 0, 8, 3)
        },
        {
            "name": "Active Basket Items Tracked Daily",
            "desc": "Number of canonical consumer products evaluated with Jevons micro-indices.",
            "display": "scalar",
            "sql": """
                SELECT COUNT(DISTINCT item_id) AS "Active Basket Items"
                FROM gold.fct_elementary_indices
                WHERE calculation_date = (SELECT MAX(calculation_date) FROM gold.fct_elementary_indices);
            """,
            "viz": {},
            "grid": (16, 0, 8, 3)
        },

        # ROW 3: DAILY INFLATION TRENDLINE (Y=3, H=8)
        {
            "name": "Daily Headline vs Core CPI Index Trend (Time Series)",
            "desc": "Daily index trajectory comparing Headline Inflation vs Core Inflation.",
            "display": "line",
            "sql": """
                SELECT 
                    calculation_date AS "Date",
                    headline_cpi AS "Headline CPI",
                    core_cpi AS "Core CPI"
                FROM (
                    SELECT DISTINCT calculation_date, headline_cpi, core_cpi
                    FROM gold.fct_cpi_daily
                ) sub
                ORDER BY calculation_date ASC;
            """,
            "viz": {
                "graph.dimensions": ["Date"],
                "graph.metrics": ["Headline CPI", "Core CPI"]
            },
            "grid": (0, 3, 24, 8)
        },

        # ROW 11: 12-DIVISION PERFORMANCE TABLE (Y=11, H=8)
        {
            "name": "12-Division COICOP Expenditure Weights & Index Performance",
            "desc": "Detailed breakdown across all 12 UN COICOP divisions with official NIS weights.",
            "display": "table",
            "sql": """
                SELECT 
                    coicop_division AS "Division Code",
                    division_name AS "COICOP Division",
                    ROUND(weight * 100.0, 2) AS "NIS Weight (%)",
                    division_index AS "Current Index (Base 100)",
                    ROUND((division_index - 100.0)::numeric, 2) AS "Cumulative Inflation (%)",
                    item_count AS "Active Products"
                FROM gold.fct_cpi_daily
                WHERE calculation_date = (SELECT MAX(calculation_date) FROM gold.fct_cpi_daily)
                ORDER BY coicop_division ASC;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 11, 14, 8)
        },
        {
            "name": "Top Basket Price Movers (Largest Price Changes)",
            "desc": "Staple consumer goods exhibiting significant price shifts vs base period.",
            "display": "table",
            "sql": """
                SELECT 
                    i.canonical_name AS "Product Name",
                    e.coicop_division AS "Div",
                    ROUND(e.base_price_khr, 0) AS "Base Price (KHR)",
                    ROUND(e.current_price_khr, 0) AS "Current Price (KHR)",
                    ROUND((e.price_ratio - 1.0) * 100.0, 1) AS "Price Change (%)",
                    CASE WHEN e.is_imputed THEN 'Imputed' ELSE 'Observed' END AS "Method"
                FROM gold.fct_elementary_indices e
                JOIN silver.canonical_items i ON i.item_id = e.item_id
                WHERE e.calculation_date = (SELECT MAX(calculation_date) FROM gold.fct_elementary_indices)
                ORDER BY ABS(e.price_ratio - 1.0) DESC
                LIMIT 20;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (14, 11, 10, 8)
        }
    ]

    for item in cpi_cards:
        cid = create_or_update_card(cur, item["name"], item["desc"], item["display"], item["sql"], item["viz"], c_cpi, db_id=db_id)
        col, row, sx, sy = item["grid"]
        place_card_on_dashboard(cur, d_cpi_id, cid, col, row, sx, sy, item["viz"])

    # ═══════════════════════════════════════════════════════════════════════════
    # 2. 🚀 PIPELINE OPERATIONS & MONITORING DASHBOARD
    # ═══════════════════════════════════════════════════════════════════════════
    col_name_2 = "02 - Cambodia CPI Pipeline Monitoring & Data Explorer"
    dash_name_2 = "🚀 Cambodia CPI Pipeline Operations & Monitoring Dashboard"
    purge_target_collection_items(cur, col_name_2, dash_name_2, db_id=db_id)

    print("[3/4] Setting up Operations Collection...")
    c_ops = get_or_create_collection(
        cur,
        col_name_2,
        "Live DAG monitoring, incident tracking, source ingestion health, fuel prices, and dimensional fact tables.",
        "#2E5BFF"
    )

    print("[4/4] Building Operations Monitoring Dashboard...")
    d_ops_id = create_or_update_dashboard(
        cur,
        dash_name_2,
        "Live real-time monitoring of Airflow DAG runs, scraper ingestion progress, failure alerts, and Silver/Gold data warehouse tables.",
        c_ops
    )

    ops_cards = [
        # ROW 0: TOP KPI STATUS SUMMARY (Y=0, H=3)
        {
            "name": "DAGs Running In-Flight Now",
            "desc": "Count of Airflow DAGs currently actively executing right now.",
            "display": "scalar",
            "sql": """
                SELECT COUNT(*) AS "DAGs Running Now"
                FROM airflow_monitor.dag_run
                WHERE state = 'running'
                  AND DATE(start_date AT TIME ZONE 'Asia/Phnom_Penh') = (SELECT MAX(DATE(start_date AT TIME ZONE 'Asia/Phnom_Penh')) FROM airflow_monitor.dag_run);
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
                  AND DATE(start_date AT TIME ZONE 'Asia/Phnom_Penh') = (SELECT MAX(DATE(start_date AT TIME ZONE 'Asia/Phnom_Penh')) FROM airflow_monitor.task_instance);
            """,
            "viz": {},
            "grid": (4, 0, 5, 3)
        },
        {
            "name": "Total Raw Prices Scraped Today (Bronze)",
            "desc": "Total raw uncleaned price records collected across all 20 retail scrapers.",
            "display": "scalar",
            "sql": """
                SELECT COUNT(*) AS "Raw Prices Scraped Today"
                FROM bronze.raw_prices
                WHERE scraped_at::date = (SELECT MAX(scraped_at::date) FROM bronze.raw_prices);
            """,
            "viz": {},
            "grid": (9, 0, 5, 3)
        },
        {
            "name": "Cleaned Products in Silver (Latest)",
            "desc": "Unique distinct canonical items matched and cleaned in the Silver layer.",
            "display": "scalar",
            "sql": """
                SELECT COUNT(*) AS "Cleaned Products in Silver"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices);
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

        # ROW 3: LIVE DAG STATUS & FAILURE ALERT (Y=3, H=7)
        {
            "name": "Failed DAG Tasks & Ingestion Alerts (Today)",
            "desc": "Active failed DAGs requiring attention. If empty, all pipelines ran successfully.",
            "display": "table",
            "sql": """
                WITH latest_runs AS (
                    SELECT DISTINCT ON (dag_id) dag_id, state, start_date, end_date
                    FROM airflow_monitor.dag_run
                    WHERE DATE(start_date AT TIME ZONE 'Asia/Phnom_Penh') = (SELECT MAX(DATE(start_date AT TIME ZONE 'Asia/Phnom_Penh')) FROM airflow_monitor.dag_run)
                    ORDER BY dag_id, start_date DESC
                )
                SELECT 
                    ti.dag_id AS "Failed DAG",
                    ti.task_id AS "Failed Task",
                    ti.state AS "State",
                    ti.try_number AS "Attempt #",
                    TO_CHAR(ti.start_date AT TIME ZONE 'Asia/Phnom_Penh', 'HH24:MI:SS') AS "Started (ICT)",
                    TO_CHAR(ti.end_date AT TIME ZONE 'Asia/Phnom_Penh', 'HH24:MI:SS') AS "Ended (ICT)",
                    ROUND(ti.duration::numeric, 1) AS "Duration (s)"
                FROM airflow_monitor.task_instance ti
                JOIN latest_runs lr ON lr.dag_id = ti.dag_id AND lr.state = 'failed'
                WHERE DATE(ti.start_date AT TIME ZONE 'Asia/Phnom_Penh') = (SELECT MAX(DATE(start_date AT TIME ZONE 'Asia/Phnom_Penh')) FROM airflow_monitor.task_instance)
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
                WITH latest_runs AS (
                    SELECT DISTINCT ON (dag_id) 
                        dag_id,
                        state,
                        run_type,
                        start_date,
                        end_date
                    FROM airflow_monitor.dag_run
                    WHERE DATE(start_date AT TIME ZONE 'Asia/Phnom_Penh') = (SELECT MAX(DATE(start_date AT TIME ZONE 'Asia/Phnom_Penh')) FROM airflow_monitor.dag_run)
                    ORDER BY dag_id, start_date DESC
                )
                SELECT 
                    dag_id AS "DAG Name",
                    UPPER(state) AS "Status",
                    run_type AS "Run Type",
                    TO_CHAR(start_date AT TIME ZONE 'Asia/Phnom_Penh', 'HH24:MI:SS') AS "Start (ICT)",
                    TO_CHAR(end_date AT TIME ZONE 'Asia/Phnom_Penh', 'HH24:MI:SS') AS "End (ICT)",
                    ROUND(EXTRACT(EPOCH FROM (COALESCE(end_date, NOW()) - start_date))::numeric, 1) AS "Duration (s)"
                FROM latest_runs
                ORDER BY 
                    CASE WHEN state = 'running' THEN 1 WHEN state = 'failed' THEN 2 ELSE 3 END,
                    start_date DESC;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (11, 3, 13, 7)
        },

        # ROW 10: STORE INGESTION PROGRESS & HEALTH (Y=10, H=8)
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
                    SELECT DISTINCT ON (REPLACE(REPLACE(dag_id, 'scrape_', ''), '_dag', ''))
                        REPLACE(REPLACE(dag_id, 'scrape_', ''), '_dag', '') AS store_slug,
                        state,
                        start_date AT TIME ZONE 'Asia/Phnom_Penh' AS start_time,
                        end_date AT TIME ZONE 'Asia/Phnom_Penh' AS end_time
                    FROM airflow_monitor.dag_run
                    WHERE DATE(start_date AT TIME ZONE 'Asia/Phnom_Penh') = (SELECT MAX(DATE(start_date AT TIME ZONE 'Asia/Phnom_Penh')) FROM airflow_monitor.dag_run)
                      AND dag_id LIKE 'scrape_%_dag'
                    ORDER BY REPLACE(REPLACE(dag_id, 'scrape_', ''), '_dag', ''), start_date DESC
                )
                SELECT 
                    s.store_slug AS "Store Slug",
                    s.store_name AS "Store Name",
                    s.source_type AS "Channel Type",
                    COALESCE(UPPER(d.state), 'INGESTED') AS "DAG State",
                    COALESCE(ts.record_count, 0) AS "Raw Records Today",
                    CASE 
                        WHEN COALESCE(ts.record_count, 0) > 0 THEN '✅ INGESTED'
                        WHEN d.state = 'running' THEN '🔄 SCRAPING NOW'
                        WHEN d.state = 'failed' THEN '❌ FAILED'
                        ELSE '⏳ WAITING'
                    END AS "Ingest Status",
                    TO_CHAR(d.start_time, 'HH24:MI:SS') AS "Started (ICT)",
                    TO_CHAR(d.end_time, 'HH24:MI:SS') AS "Finished (ICT)"
                FROM gold.dim_stores s
                LEFT JOIN today_dags d ON d.store_slug = s.store_slug
                LEFT JOIN today_scrapes ts ON ts.store_slug = s.store_slug
                WHERE s.is_active = TRUE
                ORDER BY "Raw Records Today" DESC;
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
                    SELECT MAX(scrape_date) AS m_date FROM gold.fct_daily_prices
                ),
                today_stats AS (
                    SELECT store_slug, COUNT(*) AS count_today
                    FROM gold.fct_daily_prices, latest_date
                    WHERE scrape_date = latest_date.m_date
                    GROUP BY store_slug
                ),
                yesterday_stats AS (
                    SELECT store_slug, COUNT(*) AS count_yesterday
                    FROM gold.fct_daily_prices, latest_date
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
                FROM gold.dim_stores s
                LEFT JOIN today_stats t ON t.store_slug = s.store_slug
                LEFT JOIN yesterday_stats y ON y.store_slug = s.store_slug
                ORDER BY "Latest Ingest" DESC;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (12, 10, 12, 8)
        },

        # ROW 18: RETAIL & GASOLINE PRICES (Y=18, H=6)
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
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices)
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
        }
    ]

    for item in ops_cards:
        cid = create_or_update_card(cur, item["name"], item["desc"], item["display"], item["sql"], item["viz"], c_ops, db_id=db_id)
        col, row, sx, sy = item["grid"]
        place_card_on_dashboard(cur, d_ops_id, cid, col, row, sx, sy, item["viz"])

    cur.execute("DELETE FROM query_cache;")
    conn.commit()
    conn.close()

    print("\n=============================================================================")
    print("SUCCESS: Metabase CPI & Operations Dashboards configured!")
    print(f"  [1] CPI Inflation Dashboard ID: {d_cpi_id} | Collection ID: {c_cpi}")
    print(f"  [2] Operations Dashboard ID: {d_ops_id} | Collection ID: {c_ops}")
    print("  Metabase URL: http://localhost:3000")
    print("=============================================================================")

if __name__ == "__main__":
    provision_all()
