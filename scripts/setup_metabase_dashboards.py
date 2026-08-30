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
        },

        # AEON MULTI-CATEGORY PRODUCT BREAKDOWN
        {
            "name": "AEON Product Distribution by COICOP Division",
            "desc": "Product count and average prices across all COICOP divisions for AEON multi-category stores (aeon, aeon3).",
            "display": "bar",
            "sql": """
                WITH classified AS (
                    SELECT
                        ci.canonical_name,
                        COALESCE(cs.coicop_division, 'UNCLASSIFIED') AS coicop_division,
                        CASE
                            WHEN cs.coicop_division = '01' THEN 'Food & Non-Alc Bev'
                            WHEN cs.coicop_division = '02' THEN 'Alcohol & Tobacco'
                            WHEN cs.coicop_division = '03' THEN 'Clothing & Footwear'
                            WHEN cs.coicop_division = '05' THEN 'Household Items'
                            WHEN cs.coicop_division = '09' THEN 'Recreation & Electronics'
                            WHEN cs.coicop_division = '12' THEN 'Personal Care'
                            ELSE cs.coicop_division
                        END AS division_name,
                        fdp.unit_price_local,
                        fdp.store_slug
                    FROM silver.canonical_items ci
                    LEFT JOIN (
                        SELECT DISTINCT ON (item_id::uuid)
                            item_id::uuid AS item_id, coicop_division
                        FROM staging.int_coicop_classified
                        ORDER BY item_id::uuid,
                                 CASE WHEN coicop_division <> 'UNCLASSIFIED' THEN 1 ELSE 2 END,
                                 coicop_confidence DESC
                    ) cs ON cs.item_id = ci.item_id
                    JOIN gold.fct_daily_prices fdp ON fdp.item_id = ci.item_id::uuid
                    WHERE fdp.store_slug IN ('aeon', 'aeon3')
                      AND fdp.scrape_date = (SELECT MAX(scrape_date) FROM gold.fct_daily_prices WHERE store_slug IN ('aeon', 'aeon3'))
                )
                SELECT
                    division_name AS "COICOP Division",
                    COUNT(DISTINCT canonical_name) AS "Product Count",
                    ROUND(AVG(unit_price_local), 0) AS "Avg Price",
                    ROUND(MIN(unit_price_local), 0) AS "Min Price",
                    ROUND(MAX(unit_price_local), 0) AS "Max Price"
                FROM classified
                WHERE coicop_division <> 'UNCLASSIFIED'
                GROUP BY division_name, coicop_division
                ORDER BY coicop_division;
            """,
            "viz": {
                "graph.dimensions": ["COICOP Division"],
                "graph.metrics": ["Product Count"]
            },
            "grid": (0, 19, 12, 7)
        },
        {
            "name": "AEON Sample Products by Division (Detail)",
            "desc": "Individual product listing with names, brands, sizes, and prices across AEON stores.",
            "display": "table",
            "sql": """
                WITH classified AS (
                    SELECT
                        ci.canonical_name,
                        ci.brand,
                        ci.size_norm,
                        COALESCE(cs.coicop_division, 'UNCLASSIFIED') AS coicop_division,
                        CASE
                            WHEN cs.coicop_division = '01' THEN 'Food'
                            WHEN cs.coicop_division = '02' THEN 'Alcohol'
                            WHEN cs.coicop_division = '03' THEN 'Clothing'
                            WHEN cs.coicop_division = '05' THEN 'Household'
                            WHEN cs.coicop_division = '09' THEN 'Electronics'
                            WHEN cs.coicop_division = '12' THEN 'Personal Care'
                            ELSE 'Other'
                        END AS division_name,
                        fdp.unit_price_local,
                        fdp.store_slug,
                        fdp.currency
                    FROM silver.canonical_items ci
                    LEFT JOIN (
                        SELECT DISTINCT ON (item_id::uuid)
                            item_id::uuid AS item_id, coicop_division
                        FROM staging.int_coicop_classified
                        ORDER BY item_id::uuid,
                                 CASE WHEN coicop_division <> 'UNCLASSIFIED' THEN 1 ELSE 2 END,
                                 coicop_confidence DESC
                    ) cs ON cs.item_id = ci.item_id
                    JOIN gold.fct_daily_prices fdp ON fdp.item_id = ci.item_id::uuid
                    WHERE fdp.store_slug IN ('aeon', 'aeon3')
                      AND fdp.scrape_date = (SELECT MAX(scrape_date) FROM gold.fct_daily_prices WHERE store_slug IN ('aeon', 'aeon3'))
                )
                SELECT
                    division_name AS "Division",
                    canonical_name AS "Product Name",
                    brand AS "Brand",
                    size_norm AS "Size",
                    ROUND(unit_price_local, 0) AS "Price",
                    store_slug AS "Store"
                FROM classified
                WHERE coicop_division <> 'UNCLASSIFIED'
                ORDER BY division_name, canonical_name;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (12, 19, 12, 7)
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
                  AND store_slug IN ('moc_fuel', 'new_gasoline', 'total_energies', 'tela', 'caltex', 'ptt')
                  AND coicop_division = '07'
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

    # ═══════════════════════════════════════════════════════════════════════════
    # 3. 🕷️ SCRAPER DATA HEALTH & EXTRACTION MONITORING DASHBOARD
    # ═══════════════════════════════════════════════════════════════════════════
    col_name_3 = "03 - Scraper Data Ingestion & Quality Monitoring"
    dash_name_3 = "🕷️ Scraper Data Health & Ingestion Quality Dashboard"
    purge_target_collection_items(cur, col_name_3, dash_name_3, db_id=db_id)

    print("[5/5] Setting up Scraper Data Monitoring Collection & Dashboard...")
    c_scrape = get_or_create_collection(
        cur,
        col_name_3,
        "Comprehensive scrape ingestion volume, field extraction completeness, fallback rates, outlier detection, and COICOP classification efficiency.",
        "#509EE3"
    )

    d_scrape_id = create_or_update_dashboard(
        cur,
        dash_name_3,
        "End-to-end telemetry for web scrapers: row volume, store coverage matrix, missing fields, fallbacks, price anomalies, and classification methods.",
        c_scrape
    )

    scrape_cards = [
        # ROW 0: TOP KPI STATUS SUMMARY (Y=0, H=3)
        {
            "name": "Total Scraped Records (Latest Day)",
            "desc": "Total raw observation records scraped across all retail and market sources on the latest scrape date.",
            "display": "scalar",
            "sql": """
                SELECT COUNT(*) AS "Total Scraped Today"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices);
            """,
            "viz": {},
            "grid": (0, 0, 5, 3)
        },
        {
            "name": "Active Stores Scraped (Latest Day)",
            "desc": "Distinct active retail store channels successfully ingested on the latest scrape date.",
            "display": "scalar",
            "sql": """
                SELECT COUNT(DISTINCT store_slug) AS "Active Stores Today"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices);
            """,
            "viz": {},
            "grid": (5, 0, 5, 3)
        },
        {
            "name": "Price Outlier / Anomaly Rate (%)",
            "desc": "Percentage of scraped prices flagged as statistical outliers or abnormal swings.",
            "display": "scalar",
            "sql": """
                SELECT 
                    ROUND((COUNT(*) FILTER (WHERE is_outlier = TRUE) * 100.0 / NULLIF(COUNT(*), 0))::numeric, 2) AS "Outlier Rate (%)"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices);
            """,
            "viz": {},
            "grid": (10, 0, 5, 3)
        },
        {
            "name": "Fallback Selector Rate (%)",
            "desc": "Percentage of items extracted using scraper fallback selectors (potential website HTML structure change).",
            "display": "scalar",
            "sql": """
                SELECT 
                    ROUND((COUNT(*) FILTER (WHERE is_fallback = TRUE) * 100.0 / NULLIF(COUNT(*), 0))::numeric, 2) AS "Fallback Rate (%)"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices);
            """,
            "viz": {},
            "grid": (15, 0, 5, 3)
        },
        {
            "name": "Unclassified Products Count",
            "desc": "Items ingested today that could not be mapped to any COICOP division.",
            "display": "scalar",
            "sql": """
                SELECT COUNT(*) AS "Unclassified Items"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices)
                  AND coicop_division = 'UNCLASSIFIED';
            """,
            "viz": {},
            "grid": (20, 0, 4, 3)
        },

        # ROW 3: DAILY SCRAPE VOLUME BY STORE & STORE MATRIX (Y=3, H=8)
        {
            "name": "Daily Scraped Observation Volume by Store (Last 30 Days)",
            "desc": "Time series stacked bar chart showing record volume by store channel to detect missing runs or scrape drops.",
            "display": "bar",
            "sql": """
                SELECT 
                    scrape_date AS "Scrape Date",
                    store_slug AS "Store",
                    COUNT(*) AS "Records Scraped"
                FROM silver.clean_store_prices
                WHERE scrape_date >= (SELECT MAX(scrape_date) - INTERVAL '30 days' FROM silver.clean_store_prices)
                GROUP BY scrape_date, store_slug
                ORDER BY scrape_date ASC, store_slug;
            """,
            "viz": {
                "graph.dimensions": ["Scrape Date", "Store"],
                "graph.metrics": ["Records Scraped"],
                "stackable.stack_type": "stacked"
            },
            "grid": (0, 3, 14, 8)
        },
        {
            "name": "Store Scrape Ingestion Matrix (Last 14 Days)",
            "desc": "Matrix grid showing scraped record counts per store across recent days (detects intermittent scraper outages).",
            "display": "table",
            "sql": """
                SELECT 
                    store_slug AS "Store Slug",
                    COUNT(*) FILTER (WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices)) AS "Latest",
                    COUNT(*) FILTER (WHERE scrape_date = (SELECT MAX(scrape_date) - INTERVAL '1 day' FROM silver.clean_store_prices)) AS "D-1",
                    COUNT(*) FILTER (WHERE scrape_date = (SELECT MAX(scrape_date) - INTERVAL '2 day' FROM silver.clean_store_prices)) AS "D-2",
                    COUNT(*) FILTER (WHERE scrape_date = (SELECT MAX(scrape_date) - INTERVAL '3 day' FROM silver.clean_store_prices)) AS "D-3",
                    COUNT(*) FILTER (WHERE scrape_date = (SELECT MAX(scrape_date) - INTERVAL '4 day' FROM silver.clean_store_prices)) AS "D-4",
                    COUNT(*) FILTER (WHERE scrape_date = (SELECT MAX(scrape_date) - INTERVAL '5 day' FROM silver.clean_store_prices)) AS "D-5",
                    COUNT(*) FILTER (WHERE scrape_date = (SELECT MAX(scrape_date) - INTERVAL '6 day' FROM silver.clean_store_prices)) AS "D-6",
                    COUNT(*) AS "Total 14D Records"
                FROM silver.clean_store_prices
                WHERE scrape_date >= (SELECT MAX(scrape_date) - INTERVAL '14 days' FROM silver.clean_store_prices)
                GROUP BY store_slug
                ORDER BY "Latest" DESC, store_slug;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (14, 3, 10, 8)
        },

        # ROW 11: FIELD EXTRACTION COMPLETENESS & FALLBACK LOG (Y=11, H=8)
        {
            "name": "Scraper Field Extraction Completeness (%)",
            "desc": "Percentage of scraped rows with non-null critical metadata (barcode, brand, native category, unit size).",
            "display": "table",
            "sql": """
                SELECT 
                    store_slug AS "Store",
                    COUNT(*) AS "Total Items",
                    ROUND((COUNT(barcode) FILTER (WHERE barcode IS NOT NULL AND TRIM(barcode) <> '') * 100.0 / COUNT(*))::numeric, 1) AS "Barcode (%)",
                    ROUND((COUNT(brand) FILTER (WHERE brand IS NOT NULL AND TRIM(brand) <> '') * 100.0 / COUNT(*))::numeric, 1) AS "Brand (%)",
                    ROUND((COUNT(category_native) FILTER (WHERE category_native IS NOT NULL AND TRIM(category_native) <> '') * 100.0 / COUNT(*))::numeric, 1) AS "Category Native (%)",
                    ROUND((COUNT(size_unit) FILTER (WHERE size_unit IS NOT NULL AND TRIM(size_unit) <> '') * 100.0 / COUNT(*))::numeric, 1) AS "Unit Size (%)",
                    ROUND((COUNT(*) FILTER (WHERE on_promo = TRUE) * 100.0 / COUNT(*))::numeric, 1) AS "Promo Rate (%)"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices)
                GROUP BY store_slug
                ORDER BY "Total Items" DESC;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 11, 14, 8)
        },
        {
            "name": "COICOP Classification Method Breakdown",
            "desc": "Method distribution used to assign COICOP codes (rule override, Gemini AI cache, category map, store default).",
            "display": "bar",
            "sql": """
                SELECT 
                    COALESCE(coicop_method, 'unclassified') AS "Classification Method",
                    COUNT(*) AS "Item Count"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices)
                GROUP BY coicop_method
                ORDER BY "Item Count" DESC;
            """,
            "viz": {
                "graph.dimensions": ["Classification Method"],
                "graph.metrics": ["Item Count"]
            },
            "grid": (14, 11, 10, 8)
        },

        # ROW 19: OUTLIERS, ANOMALIES & FALLBACK AUDIT (Y=19, H=7)
        {
            "name": "Scraper Price Outliers & Anomalies Audit (Latest)",
            "desc": "Inspection table of items flagged as outliers or extreme price deviations for manual validation.",
            "display": "table",
            "sql": """
                SELECT 
                    scrape_date AS "Date",
                    store_slug AS "Store",
                    name_clean AS "Product Name",
                    price_original_curr AS "Raw Price",
                    currency AS "Currency",
                    price_khr AS "Price (KHR)",
                    coicop_division AS "Div",
                    is_outlier AS "Outlier",
                    is_fallback AS "Fallback",
                    fallback_reason AS "Fallback Reason"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices)
                  AND (is_outlier = TRUE OR is_fallback = TRUE)
                ORDER BY is_outlier DESC, price_khr DESC
                LIMIT 50;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 19, 24, 7)
        }
    ]

    for item in scrape_cards:
        cid = create_or_update_card(cur, item["name"], item["desc"], item["display"], item["sql"], item["viz"], c_scrape, db_id=db_id)
        col, row, sx, sy = item["grid"]
        place_card_on_dashboard(cur, d_scrape_id, cid, col, row, sx, sy, item["viz"])

    # ═══════════════════════════════════════════════════════════════════════════
    # 4. 🥉🥈 MEDALLION BRONZE & SILVER DATA QUALITY & OBSERVABILITY DASHBOARD
    # ═══════════════════════════════════════════════════════════════════════════
    col_name_4 = "04 - Medallion Bronze & Silver Data Quality & Observability"
    dash_name_4 = "🥉🥈 Medallion Bronze & Silver Data Observability Dashboard"
    purge_target_collection_items(cur, col_name_4, dash_name_4, db_id=db_id)

    print("[6/6] Setting up Bronze & Silver Data Quality Collection & Dashboard...")
    c_bs = get_or_create_collection(
        cur,
        col_name_4,
        "Observability dashboard tracking raw ingestion health (Bronze), cleaning and survival rates, null audits, COICOP coverage, and outlier anomalies (Silver).",
        "#FF9900"
    )

    d_bs_id = create_or_update_dashboard(
        cur,
        dash_name_4,
        "Production Data Observability for Bronze (Raw Ingestion, SLA Freshness, Schema/Scrape Errors) and Silver (Survival Rate, COICOP Classification Coverage, Outlier & Null Audits).",
        c_bs
    )

    bs_cards = [
        # ROW 0: TOP KPI TICKERS (Y=0, H=3)
        {
            "name": "Bronze Ingested Today (Raw Rows)",
            "desc": "Total raw uncleaned price records collected today across all scrapers and ingestion channels.",
            "display": "scalar",
            "sql": """
                SELECT COUNT(*) AS "Bronze Raw Ingested Today"
                FROM bronze.raw_prices
                WHERE scraped_at::date = (SELECT MAX(scraped_at::date) FROM bronze.raw_prices);
            """,
            "viz": {},
            "grid": (0, 0, 4, 3)
        },
        {
            "name": "Bronze-to-Silver Survival Rate (%)",
            "desc": "Percentage of raw records that successfully passed validation and normalization into Silver.",
            "display": "scalar",
            "sql": """
                WITH b AS (
                    SELECT COUNT(*) AS b_cnt
                    FROM bronze.raw_prices
                    WHERE scraped_at::date = (SELECT MAX(scraped_at::date) FROM bronze.raw_prices)
                ),
                s AS (
                    SELECT COUNT(*) AS s_cnt
                    FROM silver.clean_store_prices
                    WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices)
                )
                SELECT ROUND((s.s_cnt * 100.0 / NULLIF(b.b_cnt, 0))::numeric, 2) AS "Survival Rate (%)"
                FROM b, s;
            """,
            "viz": {},
            "grid": (4, 0, 4, 3)
        },
        {
            "name": "Silver Clean Records (Latest Day)",
            "desc": "Total validated and standardized records loaded into the Silver layer.",
            "display": "scalar",
            "sql": """
                SELECT COUNT(*) AS "Silver Clean Records"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices);
            """,
            "viz": {},
            "grid": (8, 0, 4, 3)
        },
        {
            "name": "COICOP Classification Coverage Rate (%)",
            "desc": "Percentage of Silver products successfully mapped to a standard COICOP division (01-12).",
            "display": "scalar",
            "sql": """
                SELECT 
                    ROUND((COUNT(*) FILTER (WHERE coicop_division IS NOT NULL AND coicop_division <> 'UNCLASSIFIED') * 100.0 / NULLIF(COUNT(*), 0))::numeric, 2) AS "Classification Coverage (%)"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices);
            """,
            "viz": {},
            "grid": (12, 0, 4, 3)
        },
        {
            "name": "Silver Price Outliers Detected",
            "desc": "Count of items flagged as statistical price outliers in the latest batch.",
            "display": "scalar",
            "sql": """
                SELECT COUNT(*) AS "Price Outliers Flagged"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices)
                  AND is_outlier = TRUE;
            """,
            "viz": {},
            "grid": (16, 0, 4, 3)
        },
        {
            "name": "Pending Human Review Queue",
            "desc": "Count of items in Silver needs_review table awaiting human resolution.",
            "display": "scalar",
            "sql": """
                SELECT COUNT(*) AS "Pending Review Items"
                FROM silver.needs_review
                WHERE status = 'pending';
            """,
            "viz": {},
            "grid": (20, 0, 4, 3)
        },

        # ROW 3: BRONZE INGESTION TELEMETRY & FRESHNESS SLA (Y=3, H=8)
        {
            "name": "Bronze Ingestion Volume by Source (Last 30 Days)",
            "desc": "Time series stacked bar chart showing raw ingested records per merchant to identify missing ingestion runs.",
            "display": "bar",
            "sql": """
                SELECT 
                    scraped_at::date AS "Ingestion Date",
                    source_name AS "Source",
                    COUNT(*) AS "Raw Records"
                FROM bronze.raw_prices
                WHERE scraped_at >= (SELECT MAX(scraped_at) - INTERVAL '30 days' FROM bronze.raw_prices)
                GROUP BY scraped_at::date, source_name
                ORDER BY scraped_at::date ASC, source_name;
            """,
            "viz": {
                "graph.dimensions": ["Ingestion Date", "Source"],
                "graph.metrics": ["Raw Records"],
                "stackable.stack_type": "stacked"
            },
            "grid": (0, 3, 14, 8)
        },
        {
            "name": "Bronze Ingestion Freshness & SLA Lag by Source",
            "desc": "Elapsed hours since last raw batch landed for each data source with color-coded SLA status.",
            "display": "table",
            "sql": """
                SELECT 
                    source_name AS "Source Name",
                    COUNT(*) AS "Total Ingested (7D)",
                    MAX(scraped_at) AS "Last Ingested (UTC)",
                    ROUND(EXTRACT(EPOCH FROM (NOW() - MAX(scraped_at))) / 3600.0, 1) AS "Lag (Hours)",
                    CASE 
                        WHEN NOW() - MAX(scraped_at) <= INTERVAL '24 hours' THEN '🟢 FRESH (<24h)'
                        WHEN NOW() - MAX(scraped_at) <= INTERVAL '48 hours' THEN '🟡 DELAYED (24-48h)'
                        ELSE '🔴 STALE (>48h)'
                    END AS "Freshness SLA"
                FROM bronze.raw_prices
                GROUP BY source_name
                ORDER BY "Lag (Hours)" ASC;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (14, 3, 10, 8)
        },

        # ROW 11: BRONZE-TO-SILVER RECONCILIATION FUNNEL & ERROR LOG (Y=11, H=8)
        {
            "name": "Bronze vs Silver Daily Reconciliation Funnel",
            "desc": "Conversion comparison between Bronze raw records and Silver clean records per day and source.",
            "display": "table",
            "sql": """
                WITH bronze_daily AS (
                    SELECT 
                        scraped_at::date AS d_date,
                        source_name AS store_key,
                        COUNT(*) AS bronze_count
                    FROM bronze.raw_prices
                    WHERE scraped_at >= (SELECT MAX(scraped_at) - INTERVAL '14 days' FROM bronze.raw_prices)
                    GROUP BY scraped_at::date, source_name
                ),
                silver_daily AS (
                    SELECT 
                        scrape_date AS d_date,
                        store_slug AS store_key,
                        COUNT(*) AS silver_count
                    FROM silver.clean_store_prices
                    WHERE scrape_date >= (SELECT MAX(scrape_date) - INTERVAL '14 days' FROM silver.clean_store_prices)
                    GROUP BY scrape_date, store_slug
                )
                SELECT 
                    COALESCE(b.d_date, s.d_date) AS "Date",
                    COALESCE(b.store_key, s.store_key) AS "Source / Store",
                    COALESCE(b.bronze_count, 0) AS "Bronze Ingested",
                    COALESCE(s.silver_count, 0) AS "Silver Cleaned",
                    COALESCE(b.bronze_count, 0) - COALESCE(s.silver_count, 0) AS "Filtered / Deduped",
                    ROUND((COALESCE(s.silver_count, 0) * 100.0 / NULLIF(b.bronze_count, 0))::numeric, 1) AS "Survival Rate (%)"
                FROM bronze_daily b
                FULL OUTER JOIN silver_daily s ON b.d_date = s.d_date AND b.store_key = s.store_key
                ORDER BY "Date" DESC, "Bronze Ingested" DESC;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 11, 14, 8)
        },
        {
            "name": "Bronze Scrape Errors & Ingestion Exceptions Log",
            "desc": "Detailed log of unparsable payloads, extraction errors, and network failures in Bronze.",
            "display": "table",
            "sql": """
                SELECT 
                    created_at AT TIME ZONE 'Asia/Phnom_Penh' AS "Timestamp (ICT)",
                    source_name AS "Source",
                    error_type AS "Error Category",
                    LEFT(error_message, 100) AS "Error Message",
                    LEFT(raw_record, 60) AS "Raw Sample"
                FROM bronze.scrape_errors
                ORDER BY created_at DESC
                LIMIT 30;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (14, 11, 10, 8)
        },

        # ROW 19: SILVER CATEGORIZATION & ATTRIBUTE COMPLETENESS (Y=19, H=8)
        {
            "name": "Silver COICOP Classification Product Breakdown",
            "desc": "Product count distribution across all 12 COICOP divisions in the Silver layer.",
            "display": "bar",
            "sql": """
                SELECT 
                    COALESCE(coicop_division, 'UNCLASSIFIED') AS "COICOP Division",
                    COUNT(*) AS "Product Count"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices)
                GROUP BY coicop_division
                ORDER BY "Product Count" DESC;
            """,
            "viz": {
                "graph.dimensions": ["COICOP Division"],
                "graph.metrics": ["Product Count"]
            },
            "grid": (0, 19, 10, 8)
        },
        {
            "name": "Silver Field Null & Attribute Completeness Audit",
            "desc": "Completeness audit of barcode, brand, category, size unit, and COICOP mapping across stores in Silver.",
            "display": "table",
            "sql": """
                SELECT 
                    store_slug AS "Store Channel",
                    COUNT(*) AS "Total Clean Items",
                    ROUND((COUNT(barcode) FILTER (WHERE barcode IS NOT NULL AND TRIM(barcode) <> '') * 100.0 / COUNT(*))::numeric, 1) AS "Barcode (%)",
                    ROUND((COUNT(brand) FILTER (WHERE brand IS NOT NULL AND TRIM(brand) <> '') * 100.0 / COUNT(*))::numeric, 1) AS "Brand (%)",
                    ROUND((COUNT(category_native) FILTER (WHERE category_native IS NOT NULL AND TRIM(category_native) <> '') * 100.0 / COUNT(*))::numeric, 1) AS "Category (%)",
                    ROUND((COUNT(size_unit) FILTER (WHERE size_unit IS NOT NULL AND TRIM(size_unit) <> '') * 100.0 / COUNT(*))::numeric, 1) AS "Unit Size (%)",
                    ROUND((COUNT(*) FILTER (WHERE coicop_division IS NOT NULL AND coicop_division <> 'UNCLASSIFIED') * 100.0 / COUNT(*))::numeric, 1) AS "COICOP Classified (%)"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices)
                GROUP BY store_slug
                ORDER BY "Total Clean Items" DESC;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (10, 19, 14, 8)
        },

        # ROW 27: SILVER OUTLIERS & NEEDS REVIEW QUEUE (Y=27, H=7)
        {
            "name": "Silver Flagged Price Outliers & Fallback Audits",
            "desc": "High-risk records flagged for price abnormalities or scraper selector fallbacks in Silver.",
            "display": "table",
            "sql": """
                SELECT 
                    scrape_date AS "Date",
                    store_slug AS "Store",
                    name_clean AS "Product Name",
                    price_khr AS "Price (KHR)",
                    unit_price_khr AS "Unit Price (KHR)",
                    coicop_division AS "Div",
                    is_outlier AS "Outlier",
                    fallback_reason AS "Audit Reason"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices)
                  AND (is_outlier = TRUE OR is_fallback = TRUE)
                ORDER BY is_outlier DESC, price_khr DESC
                LIMIT 30;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 27, 14, 7)
        },
        {
            "name": "Silver Needs Review Queue (Fuzzy Matching)",
            "desc": "Low-confidence or ambiguous items routed for human review in Silver layer.",
            "display": "table",
            "sql": """
                SELECT 
                    review_id AS "ID",
                    TO_CHAR(created_at AT TIME ZONE 'Asia/Phnom_Penh', 'YYYY-MM-DD HH24:MI') AS "Queued (ICT)",
                    LEFT(item_description_raw, 40) AS "Raw Description",
                    LEFT(best_match_name, 35) AS "Matched Name",
                    ROUND(confidence * 100.0, 1) AS "Confidence (%)",
                    status AS "Status"
                FROM silver.needs_review
                ORDER BY created_at DESC
                LIMIT 30;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (14, 27, 10, 7)
        }
    ]

    for item in bs_cards:
        cid = create_or_update_card(cur, item["name"], item["desc"], item["display"], item["sql"], item["viz"], c_bs, db_id=db_id)
        col, row, sx, sy = item["grid"]
        place_card_on_dashboard(cur, d_bs_id, cid, col, row, sx, sy, item["viz"])

    cur.execute("DELETE FROM query_cache;")
    conn.commit()
    conn.close()

    print("\n=============================================================================")
    print("SUCCESS: Metabase CPI, Operations, Scraper & Observability Dashboards configured!")
    print(f"  [1] CPI Inflation Dashboard ID: {d_cpi_id} | Collection ID: {c_cpi}")
    print(f"  [2] Operations Dashboard ID: {d_ops_id} | Collection ID: {c_ops}")
    print(f"  [3] Scraper Quality Dashboard ID: {d_scrape_id} | Collection ID: {c_scrape}")
    print(f"  [4] Bronze/Silver Observability Dashboard ID: {d_bs_id} | Collection ID: {c_bs}")
    print("  Metabase URL: http://localhost:3001 (or :3000)")
    print("=============================================================================")

if __name__ == "__main__":
    provision_all()

