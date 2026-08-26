"""
=============================================================================
CAMBODIA CPI PIPELINE — METABASE OPERATIONS & MONITORING PROVISIONER
Provisions:
  1. Pipeline Operations & Real-Time DAG Monitoring Dashboard
  2. Human Review & Data Quality Curation Hub (Unmatched Items, COICOP Queue, Outliers)
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

def get_metabase_cpi_db_id(cur) -> int:
    cur.execute("""
        SELECT id FROM metabase_database 
        WHERE name ILIKE '%cpi%' OR name ILIKE '%postgres%'
        ORDER BY CASE WHEN name ILIKE '%cpi%' THEN 1 ELSE 2 END, id DESC
        LIMIT 1;
    """)
    row = cur.fetchone()
    return row[0] if row else 2

def purge_target_collection_items(cur, target_collection_name, target_dashboard_name, db_id=2):
    cur.execute("""
        DELETE FROM report_dashboardcard 
        WHERE dashboard_id IN (
            SELECT id FROM report_dashboard 
            WHERE name = %s
        );
    """, (target_dashboard_name,))

    try:
        cpi_conn = get_db_connection("cpi_db")
        cpi_cur = cpi_conn.cursor()
        cpi_cur.execute("""
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema IN ('bronze', 'silver', 'gold', 'staging', 'airflow_monitor');
        """)
        real_tables = set(cpi_cur.fetchall())
        cpi_conn.close()

        cur.execute("SELECT id, schema, name, active FROM metabase_table WHERE db_id = %s;", (db_id,))
        all_mb_tables = cur.fetchall()
        for tid, tschema, tname, active in all_mb_tables:
            if (tschema, tname) not in real_tables or active is False:
                cur.execute("DELETE FROM metabase_fieldvalues WHERE field_id IN (SELECT id FROM metabase_field WHERE table_id = %s);", (tid,))
                cur.execute("DELETE FROM metabase_field WHERE table_id = %s;", (tid,))
                cur.execute("DELETE FROM metabase_table WHERE id = %s;", (tid,))

        visible_tables = {
            ('bronze', 'raw_prices'),
            ('bronze', 'scrape_errors'),
            ('staging', 'raw_scrapes'),
            ('staging', 'exchange_rates'),
            ('silver', 'clean_store_prices'),
            ('silver', 'canonical_items'),
            ('silver', 'needs_review'),
            ('silver', 'classification_queue'),
            ('silver', 'coicop_override_manual'),
            ('gold', 'dim_items'),
            ('gold', 'dim_stores'),
            ('gold', 'fct_daily_prices'),
            ('gold', 'v_coverage'),
            ('gold', 'v_monitor_scraper_daily'),
            ('gold', 'v_monitor_source_health_matrix'),
            ('gold', 'v_monitor_price_alerts')
        }

        now = datetime.now(timezone.utc)
        for schema_name, tbl_name in real_tables:
            cur.execute("SELECT id FROM metabase_table WHERE db_id = %s AND schema = %s AND name = %s;", (db_id, schema_name, tbl_name))
            row = cur.fetchone()
            vis_type = None if (schema_name, tbl_name) in visible_tables else 'hidden'
            display_title = tbl_name.replace('_', ' ').title()
            if row:
                cur.execute("""
                    UPDATE metabase_table
                    SET active = true, visibility_type = %s, updated_at = %s
                    WHERE id = %s;
                """, (vis_type, now, row[0]))
            else:
                cur.execute("""
                    INSERT INTO metabase_table (
                        created_at, updated_at, name, schema, display_name, active,
                        db_id, visibility_type, initial_sync_status
                    )
                    VALUES (%s, %s, %s, %s, %s, true, %s, %s, 'complete');
                """, (now, now, tbl_name, schema_name, display_title, db_id, vis_type))
    except Exception as e:
        print(f"Warning syncing schema tables: {e}")

def provision_all():
    conn = get_db_connection("metabase")
    cur = conn.cursor()
    db_id = get_metabase_cpi_db_id(cur)

    # ═══════════════════════════════════════════════════════════════════════════
    # 1. OPERATIONS & PIPELINE MONITORING DASHBOARD
    # ═══════════════════════════════════════════════════════════════════════════
    col_name_1 = "01 - Cambodia CPI Pipeline Monitoring & Data Explorer"
    dash_name_1 = "Cambodia CPI Pipeline Operations & Monitoring Dashboard"
    purge_target_collection_items(cur, col_name_1, dash_name_1, db_id=db_id)
    
    print("[1/4] Setting up Operations Collection...")
    c_ops = get_or_create_collection(
        cur, 
        col_name_1, 
        "Live DAG monitoring, incident tracking, source ingestion health, fuel prices, and dimensional fact tables", 
        "#2E5BFF"
    )

    print("[2/4] Building Dedicated Operations & Data Monitoring Dashboard...")
    d_ops_id = create_or_update_dashboard(
        cur, 
        dash_name_1, 
        "Live real-time monitoring of Airflow DAG runs, scraper ingestion progress, failure alerts, and Silver/Gold data warehouse tables.", 
        c_ops
    )

    cur.execute("DELETE FROM report_dashboardcard WHERE dashboard_id = %s;", (d_ops_id,))
    cur.execute("DELETE FROM report_card WHERE collection_id = %s;", (c_ops,))

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
            "name": "Total Raw Prices Scraped Today (Bronze)",
            "desc": "Total raw uncleaned price observations successfully ingested into bronze.raw_prices today.",
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
            "desc": "Total cleaned and validated product price quotes in silver.clean_store_prices.",
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
                    WHERE DATE(start_date AT TIME ZONE 'Asia/Phnom_Penh') = CURRENT_DATE
                      AND dag_id LIKE 'scrape_%_dag'
                    ORDER BY REPLACE(REPLACE(dag_id, 'scrape_', ''), '_dag', ''), start_date DESC
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
                FROM gold.dim_stores s
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
        },

        # ROW 24: CORE DIMENSION & FACT TABLES (Y=24..48)
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
                FROM gold.dim_stores
                ORDER BY store_slug ASC;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 24, 24, 6)
        },
        {
            "name": "Table: dim_product (gold.dim_items)",
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
                FROM gold.dim_items
                ORDER BY canonical_name ASC
                LIMIT 500;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 30, 24, 8)
        },
        {
            "name": "Table: fact_daily_price (gold.fct_daily_prices)",
            "desc": "Atomic fact table containing daily cleaned price quotes, unit prices, promotions, and outlier flags.",
            "display": "table",
            "sql": """
                SELECT 
                    f.scrape_date AS "Scrape Date",
                    f.item_id AS "Item ID",
                    m.canonical_name AS "Product Title",
                    f.store_slug AS "Store",
                    f.price_khr AS "Price (KHR)",
                    f.unit_price_khr AS "Unit Price (KHR)",
                    m.coicop_division AS "COICOP Division",
                    f.on_promo AS "On Promo",
                    f.cpi_eligible AS "CPI Eligible",
                    f.is_outlier AS "Is Outlier"
                FROM gold.fct_daily_prices f
                LEFT JOIN gold.dim_items m ON m.item_id = f.item_id
                WHERE f.scrape_date = (SELECT MAX(scrape_date) FROM gold.fct_daily_prices)
                ORDER BY f.price_khr DESC
                LIMIT 500;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 38, 24, 9)
        },
        {
            "name": "Table: silver.clean_store_prices (Unified Clean Store Fact)",
            "desc": "Unified silver store observation table containing cleaned and classified price records from all 20 scrapers.",
            "display": "table",
            "sql": """
                SELECT 
                    scrape_date AS "Scrape Date",
                    store_slug AS "Store",
                    item_id AS "Item ID",
                    name_clean AS "Clean Product Title",
                    price_khr AS "Price (KHR)",
                    unit_price_khr AS "Unit Price (KHR)",
                    coicop_division AS "COICOP Division",
                    coicop_code AS "COICOP Code",
                    on_promo AS "On Promo",
                    is_outlier AS "Is Outlier",
                    is_fallback AS "Is Fallback",
                    coicop_method AS "Classification Method"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices)
                ORDER BY scrape_date DESC, price_khr DESC
                LIMIT 500;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 47, 24, 9)
        },
        {
            "name": "Table: bronze.raw_prices (Raw Ingested Records)",
            "desc": "Raw uncleaned price observations exactly as scraped and staged from all 20 online retail channels.",
            "display": "table",
            "sql": """
                SELECT 
                    raw_price_id AS "Raw ID",
                    scraped_at::date AS "Scrape Date",
                    store_id AS "Store",
                    item_description_raw AS "Raw Product Name",
                    price AS "Raw Price",
                    currency AS "Currency",
                    raw_payload->>'category_native' AS "Native Category",
                    scraped_at AS "Scraped Timestamp"
                FROM bronze.raw_prices
                WHERE scraped_at::date = (SELECT MAX(scraped_at::date) FROM bronze.raw_prices)
                ORDER BY scraped_at::date DESC, raw_price_id DESC
                LIMIT 500;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 56, 24, 9)
        }
    ]

    for item in ops_cards:
        cid = create_or_update_card(cur, item["name"], item["desc"], item["display"], item["sql"], item["viz"], c_ops, db_id=db_id)
        col, row, sx, sy = item["grid"]
        place_card_on_dashboard(cur, d_ops_id, cid, col, row, sx, sy, item["viz"])

    # ═══════════════════════════════════════════════════════════════════════════
    # 2. HUMAN REVIEW & DATA QUALITY CURATION HUB DASHBOARD
    # ═══════════════════════════════════════════════════════════════════════════
    col_name_2 = "02 - Human Review & Data Quality Curation"
    dash_name_2 = "Cambodia CPI — Human Review & Data Curation Hub"
    purge_target_collection_items(cur, col_name_2, dash_name_2, db_id=db_id)

    print("[3/4] Setting up Human Review Collection...")
    c_rev = get_or_create_collection(
        cur,
        col_name_2,
        "Curator hub for resolving ambiguous item matches, approving COICOP classifications, and reviewing price outliers.",
        "#E87722"
    )

    print("[4/4] Building Dedicated Human Review & Curation Dashboard...")
    d_rev_id = create_or_update_dashboard(
        cur,
        dash_name_2,
        "Interactive operations workspace for price index analysts to review fuzzy-match ambiguities, audit classification queues, and inspect price spikes.",
        c_rev
    )

    cur.execute("DELETE FROM report_dashboardcard WHERE dashboard_id = %s;", (d_rev_id,))
    cur.execute("DELETE FROM report_card WHERE collection_id = %s;", (c_rev,))

    rev_cards = [
        # ROW 0: TOP REVIEW KPIS (Y=0, H=3)
        {
            "name": "Pending Item Matching Reviews",
            "desc": "Observations in silver.needs_review awaiting human curator decision.",
            "display": "scalar",
            "sql": """
                SELECT COUNT(*) AS "Pending Matching Reviews"
                FROM silver.needs_review
                WHERE status = 'pending';
            """,
            "viz": {},
            "grid": (0, 0, 6, 3)
        },
        {
            "name": "Pending COICOP Classification Queue",
            "desc": "Unclassified or low-confidence products in silver.classification_queue.",
            "display": "scalar",
            "sql": """
                SELECT COUNT(*) AS "Pending COICOP Reviews"
                FROM silver.classification_queue
                WHERE status = 'PENDING';
            """,
            "viz": {},
            "grid": (6, 0, 6, 3)
        },
        {
            "name": "Active Manual COICOP Overrides",
            "desc": "Total human classification rules active in silver.coicop_override_manual.",
            "display": "scalar",
            "sql": """
                SELECT COUNT(*) AS "Active Manual Overrides"
                FROM silver.coicop_override_manual;
            """,
            "viz": {},
            "grid": (12, 0, 6, 3)
        },
        {
            "name": "Flagged Price Outliers (Latest Scrape)",
            "desc": "Extreme price spikes or anomalous observations flagged for curator audit.",
            "display": "scalar",
            "sql": """
                SELECT COUNT(*) AS "Flagged Price Outliers"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices)
                  AND is_outlier = TRUE;
            """,
            "viz": {},
            "grid": (18, 0, 6, 3)
        },

        # ROW 3: UNMATCHED ITEMS QUEUE (Y=3, H=9)
        {
            "name": "Unmatched Items Review Queue (Needs Analyst Approval)",
            "desc": "Product titles with fuzzy matching scores between 0.85 and 0.95 requiring verification before canonical deduplication.",
            "display": "table",
            "sql": """
                SELECT 
                    nr.review_id AS "Review ID",
                    rp.store_id AS "Store",
                    nr.item_description_raw AS "Raw Scraped Product Name",
                    nr.best_match_name AS "Suggested Canonical Match",
                    ROUND(nr.confidence::numeric * 100, 1) AS "Match Conf (%)",
                    rp.price AS "Raw Price",
                    rp.currency AS "Currency",
                    nr.status AS "Review Status",
                    nr.created_at AS "Queued Timestamp"
                FROM silver.needs_review nr
                JOIN bronze.raw_prices rp ON rp.raw_price_id = nr.raw_price_id
                WHERE nr.status = 'pending'
                ORDER BY nr.confidence DESC, nr.review_id ASC
                LIMIT 500;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 3, 24, 9)
        },

        # ROW 12: COICOP CLASSIFICATION QUEUE (Y=12, H=8)
        {
            "name": "Unclassified / Low-Confidence Products Queue (COICOP)",
            "desc": "Products tagged as UNCLASSIFIED or REVIEW that need category assignment in silver.coicop_override_manual.",
            "display": "table",
            "sql": """
                SELECT 
                    product_key AS "Product Key / Item ID",
                    store_slug AS "Store",
                    name_clean AS "Clean Product Title",
                    category_native AS "Native Category",
                    price_khr AS "Price (KHR)",
                    reason AS "Queue Reason",
                    status AS "Status",
                    created_at AS "Queued Date"
                FROM silver.classification_queue
                WHERE status = 'PENDING'
                ORDER BY created_at DESC, name_clean ASC
                LIMIT 500;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 12, 24, 8)
        },

        # ROW 20: MANUAL OVERRIDES & OUTLIERS (Y=20, H=8)
        {
            "name": "Manual Classification Overrides Log (Human Decisions)",
            "desc": "Audit trail of analyst overrides applied to COICOP divisions.",
            "display": "table",
            "sql": """
                SELECT 
                    id AS "Override ID",
                    match_type AS "Match Type",
                    match_value AS "Keyword / Value",
                    COALESCE(store_slug, 'GLOBAL (All Stores)') AS "Store Scope",
                    coicop_division AS "COICOP Division",
                    reason AS "Rationale / Justification",
                    created_at AS "Date Created"
                FROM silver.coicop_override_manual
                ORDER BY created_at DESC;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 20, 12, 8)
        },
        {
            "name": "Flagged Price Outliers & Anomalies (Latest Scrapes)",
            "desc": "Observations exceeding statistical price bounds or extreme discounts/spikes.",
            "display": "table",
            "sql": """
                SELECT 
                    raw_price_id AS "Raw ID",
                    store_slug AS "Store",
                    name_clean AS "Product Name",
                    price_original_curr AS "Original Scraped Price",
                    currency AS "Currency",
                    price_khr AS "Price (KHR)",
                    discount_pct AS "Discount (%)",
                    coicop_division AS "COICOP Div",
                    scrape_date AS "Scrape Date"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices)
                  AND is_outlier = TRUE
                ORDER BY price_khr DESC
                LIMIT 200;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (12, 20, 12, 8)
        }
    ]

    for item in rev_cards:
        cid = create_or_update_card(cur, item["name"], item["desc"], item["display"], item["sql"], item["viz"], c_rev, db_id=db_id)
        col, row, sx, sy = item["grid"]
        place_card_on_dashboard(cur, d_rev_id, cid, col, row, sx, sy, item["viz"])

    conn.commit()
    conn.close()
    print("\n=============================================================================")
    print("SUCCESS: Metabase Operations & Human Review Dashboards configured!")
    print(f"  Operations Dashboard ID: {d_ops_id}   | Collection ID: {c_ops}")
    print(f"  Human Review Dashboard ID: {d_rev_id} | Collection ID: {c_rev}")
    print("  Metabase URL: http://localhost:3000")
    print("=============================================================================")

if __name__ == "__main__":
    provision_all()
