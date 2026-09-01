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

def purge_all_cpi_collections(cur):
    try:
        cur.execute("DELETE FROM report_dashboardcard;")
        cur.execute("DELETE FROM report_dashboard;")
        cur.execute("DELETE FROM report_card;")
        cur.execute("DELETE FROM collection WHERE id > 1;")
        cur.execute("DELETE FROM query_cache;")
    except Exception as e:
        print(f"Notice during purge: {e}")

def provision_all():
    conn = get_db_connection("metabase")
    cur = conn.cursor()
    db_id = get_metabase_cpi_db_id(cur)

    print("Cleaning up old Metabase collections and dashboards...")
    purge_all_cpi_collections(cur)

    # ═══════════════════════════════════════════════════════════════════════════
    # 1. 🇰🇭 CAMBODIA CPI & INFLATION EXECUTIVE DASHBOARD (Macro Policy)
    # ═══════════════════════════════════════════════════════════════════════════
    col_name_1 = "01 - Cambodia Daily CPI & Inflation Analytics"
    dash_name_1 = "🇰🇭 Cambodia Daily Consumer Price Index (CPI) Dashboard"

    print("[1/5] Setting up Collection 01: CPI Macro & Inflation Analytics...")
    c_cpi = get_or_create_collection(
        cur,
        col_name_1,
        "Official macroeconomic inflation indicators, Headline vs Core CPI, and 12-division COICOP performance.",
        "#008080"
    )

    d_cpi_id = create_or_update_dashboard(
        cur,
        dash_name_1,
        "Daily Consumer Price Index (CPI) tracking headline inflation, core inflation, and 12-division COICOP movements.",
        c_cpi
    )

    cpi_cards = [
        {
            "name": "Latest Monthly Headline CPI (Base 100)",
            "desc": "Conformed monthly headline consumer price index weighted across all 12 UN COICOP divisions.",
            "display": "scalar",
            "sql": """
                SELECT ROUND(monthly_headline_cpi::numeric, 2) AS "Monthly Headline CPI"
                FROM gold.v_cpi_monthly_summary
                ORDER BY cpi_month DESC
                LIMIT 1;
            """,
            "viz": {},
            "grid": (0, 0, 6, 3)
        },
        {
            "name": "Monthly Headline MoM Inflation (%)",
            "desc": "Month-over-Month percentage change in national headline consumer prices.",
            "display": "scalar",
            "sql": """
                SELECT COALESCE(headline_mom_inflation_pct, 0.0) AS "Headline MoM (%)"
                FROM gold.v_cpi_monthly_summary
                ORDER BY cpi_month DESC
                LIMIT 1;
            """,
            "viz": {},
            "grid": (6, 0, 6, 3)
        },
        {
            "name": "Monthly Core MoM Inflation (%)",
            "desc": "Month-over-Month percentage change in Core CPI (excluding volatile Food & Fuel).",
            "display": "scalar",
            "sql": """
                SELECT COALESCE(core_mom_inflation_pct, 0.0) AS "Core MoM (%)"
                FROM gold.v_cpi_monthly_summary
                ORDER BY cpi_month DESC
                LIMIT 1;
            """,
            "viz": {},
            "grid": (12, 0, 6, 3)
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
            "grid": (18, 0, 6, 3)
        },
        {
            "name": "Monthly Headline vs Core CPI Trajectory (MoM Time Series)",
            "desc": "Conformed monthly index trajectory comparing Headline Inflation vs Core Inflation.",
            "display": "line",
            "sql": """
                SELECT 
                    cpi_month AS "Month",
                    monthly_headline_cpi AS "Monthly Headline CPI",
                    monthly_core_cpi AS "Monthly Core CPI"
                FROM gold.v_cpi_monthly_summary
                ORDER BY cpi_month ASC;
            """,
            "viz": {
                "graph.dimensions": ["Month"],
                "graph.metrics": ["Monthly Headline CPI", "Monthly Core CPI"]
            },
            "grid": (0, 3, 24, 8)
        },
        {
            "name": "Monthly 12-Division COICOP Matrix & MoM Changes",
            "desc": "Detailed monthly breakdown across all 12 UN COICOP divisions with official NIS weights and MoM inflation rates.",
            "display": "table",
            "sql": """
                SELECT 
                    coicop_division AS "Division Code",
                    division_name AS "COICOP Division",
                    ROUND(weight * 100.0, 2) AS "NIS Weight (%)",
                    monthly_division_index AS "Monthly Index",
                    division_mom_change_pct AS "MoM Change (%)",
                    total_observations AS "Monthly Observations"
                FROM gold.v_cpi_monthly_divisions
                WHERE cpi_month = (SELECT MAX(cpi_month) FROM gold.v_cpi_monthly_divisions)
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
    # 2. 📊 PRE-CPI ECONOMETRIC DATA DIAGNOSTICS (Quality Screening)
    # ═══════════════════════════════════════════════════════════════════════════
    col_name_2 = "02 - Pre-CPI Econometric Data Diagnostics"
    dash_name_2 = "📊 Pre-CPI Econometric Data Visualization & Screening Dashboard"

    print("[2/5] Setting up Collection 02: Pre-CPI Econometric QA Screener...")
    c_pre = get_or_create_collection(
        cur,
        col_name_2,
        "Econometric data screening prior to Jevons calculation: log-relative bell curves, price spells, clearance dumps, and imputation exposure.",
        "#E67E22"
    )

    d_pre_id = create_or_update_dashboard(
        cur,
        dash_name_2,
        "Pre-CPI econometric screening validating price quotes before running elementary Jevons calculations.",
        c_pre
    )

    pre_cpi_cards = [
        {
            "name": "Total Clean Price Quotes (Pre-Calculation)",
            "desc": "Total valid clean price quotes available for the current calculation cycle.",
            "display": "scalar",
            "sql": """
                SELECT COUNT(*) AS "Clean Quotes Today"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices)
                  AND price_khr > 0;
            """,
            "viz": {},
            "grid": (0, 0, 6, 3)
        },
        {
            "name": "CPI Price Outliers Quarantined",
            "desc": "Price observations flagged as extreme statistical outliers (excluded from Jevons).",
            "display": "scalar",
            "sql": """
                SELECT COUNT(*) AS "Outliers Quarantined"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices)
                  AND is_outlier = TRUE;
            """,
            "viz": {},
            "grid": (6, 0, 6, 3)
        },
        {
            "name": "Live Observed Basket Share (%)",
            "desc": "Percentage of basket items directly observed in retail stores (vs synthetically imputed).",
            "display": "scalar",
            "sql": """
                SELECT 
                    ROUND((COUNT(*) FILTER (WHERE is_imputed = FALSE) * 100.0 / NULLIF(COUNT(*), 0))::numeric, 1) AS "Live Observed Share (%)"
                FROM gold.fct_elementary_indices
                WHERE calculation_date = (SELECT MAX(calculation_date) FROM gold.fct_elementary_indices);
            """,
            "viz": {},
            "grid": (12, 0, 6, 3)
        },
        {
            "name": "Pre-CPI Quality Gate Status",
            "desc": "Axiomatic readiness status for running Jevons elementary index calculation.",
            "display": "scalar",
            "sql": """
                SELECT 
                    CASE 
                        WHEN COUNT(*) FILTER (WHERE price_khr <= 0) > 0 THEN '❌ FAILED (Zero Prices)'
                        WHEN COUNT(*) FILTER (WHERE is_outlier = TRUE) > 500 THEN '⚠️ WARNING (High Outliers)'
                        ELSE '✅ PASS: SAFE FOR JEVONS'
                    END AS "Pre-CPI Quality Gate"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices);
            """,
            "viz": {},
            "grid": (18, 0, 6, 3)
        },
        {
            "name": "Log-Price Relative Distribution (Hadi / Tukey Outlier Check)",
            "desc": "Histogram of ln(P_t / P_t-1) checking for standard bell curve and catching 10x decimal errors.",
            "display": "bar",
            "sql": """
                WITH prev_date AS (
                    SELECT DISTINCT scrape_date 
                    FROM silver.clean_store_prices 
                    WHERE scrape_date < (SELECT MAX(scrape_date) FROM silver.clean_store_prices)
                    ORDER BY scrape_date DESC LIMIT 1
                ),
                relatives AS (
                    SELECT 
                        ROUND(LN(curr.price_khr / prev.price_khr)::numeric, 1) AS log_relative
                    FROM silver.clean_store_prices curr
                    JOIN silver.clean_store_prices prev 
                      ON curr.item_id = prev.item_id 
                     AND curr.store_slug = prev.store_slug
                    WHERE curr.scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices)
                      AND prev.scrape_date = (SELECT scrape_date FROM prev_date)
                      AND curr.price_khr > 0 
                      AND prev.price_khr > 0
                )
                SELECT 
                    log_relative AS "Log Price Relative [ln(Pt/Pt-1)]",
                    COUNT(*) AS "Observation Count"
                FROM relatives
                WHERE log_relative BETWEEN -2.5 AND 2.5
                GROUP BY log_relative
                ORDER BY log_relative ASC;
            """,
            "viz": {
                "graph.dimensions": ["Log Price Relative [ln(Pt/Pt-1)]"],
                "graph.metrics": ["Observation Count"]
            },
            "grid": (0, 3, 12, 8)
        },
        {
            "name": "Basket Imputation & Missingness Rate by COICOP Division",
            "desc": "Share of active items requiring 7-day ILO class-mean geometric imputation per division.",
            "display": "bar",
            "sql": """
                SELECT 
                    coicop_division AS "Division Code",
                    COUNT(*) AS "Total Basket Items",
                    COUNT(*) FILTER (WHERE is_imputed = TRUE) AS "Imputed Items",
                    ROUND((COUNT(*) FILTER (WHERE is_imputed = TRUE) * 100.0 / NULLIF(COUNT(*), 0))::numeric, 1) AS "Imputation Rate (%)"
                FROM gold.fct_elementary_indices
                WHERE calculation_date = (SELECT MAX(calculation_date) FROM gold.fct_elementary_indices)
                GROUP BY coicop_division
                ORDER BY coicop_division ASC;
            """,
            "viz": {
                "graph.dimensions": ["Division Code"],
                "graph.metrics": ["Imputation Rate (%)"]
            },
            "grid": (12, 3, 12, 8)
        },
        {
            "name": "Pre-Flight Extreme Price Spikes & Drops (>25% DoD)",
            "desc": "Pre-aggregation outlier table capturing single-day jumps or drops exceeding 25%.",
            "display": "table",
            "sql": """
                WITH prev_date AS (
                    SELECT DISTINCT scrape_date 
                    FROM silver.clean_store_prices 
                    WHERE scrape_date < (SELECT MAX(scrape_date) FROM silver.clean_store_prices)
                    ORDER BY scrape_date DESC LIMIT 1
                )
                SELECT 
                    curr.store_slug AS "Store",
                    LEFT(curr.name_clean, 35) AS "Product Name",
                    curr.coicop_division AS "Div",
                    ROUND(prev.price_khr, 0) AS "Prev Price (KHR)",
                    ROUND(curr.price_khr, 0) AS "Today Price (KHR)",
                    ROUND(((curr.price_khr / NULLIF(prev.price_khr, 0)) - 1.0) * 100.0, 1) AS "Shift (%)",
                    CASE WHEN curr.discount_pct > 0 THEN 'PROMO ' || curr.discount_pct || '%' ELSE 'REGULAR' END AS "Promo State"
                FROM silver.clean_store_prices curr
                JOIN silver.clean_store_prices prev 
                  ON curr.item_id = prev.item_id 
                 AND curr.store_slug = prev.store_slug
                WHERE curr.scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices)
                  AND prev.scrape_date = (SELECT scrape_date FROM prev_date)
                  AND curr.price_khr > 0 
                  AND prev.price_khr > 0
                  AND ABS((curr.price_khr / NULLIF(prev.price_khr, 0)) - 1.0) > 0.25
                ORDER BY ABS((curr.price_khr / NULLIF(prev.price_khr, 0)) - 1.0) DESC
                LIMIT 25;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 11, 14, 8)
        },
        {
            "name": "Benchmark Commodity Price Trajectories (Price Spells)",
            "desc": "Time series of staple goods checking for sticky price step-functions.",
            "display": "line",
            "sql": """
                SELECT 
                    scrape_date AS "Date",
                    store_slug || ' - ' || LEFT(name_clean, 20) AS "Commodity SKU",
                    AVG(unit_price_khr) AS "Unit Price (KHR/kg or L)"
                FROM silver.clean_store_prices
                WHERE coicop_division IN ('01', '07')
                  AND name_clean ILIKE ANY (ARRAY['%rice%', '%gasoline%', '%oil%', '%milk%', '%pork%'])
                  AND scrape_date >= (SELECT MAX(scrape_date) FROM silver.clean_store_prices) - INTERVAL '14 days'
                  AND is_outlier = FALSE
                  AND unit_price_khr > 0
                GROUP BY scrape_date, store_slug, name_clean
                ORDER BY scrape_date ASC;
            """,
            "viz": {
                "graph.dimensions": ["Date"],
                "graph.metrics": ["Unit Price (KHR/kg or L)"]
            },
            "grid": (14, 11, 10, 8)
        }
    ]

    for item in pre_cpi_cards:
        cid = create_or_update_card(cur, item["name"], item["desc"], item["display"], item["sql"], item["viz"], c_pre, db_id=db_id)
        col, row, sx, sy = item["grid"]
        place_card_on_dashboard(cur, d_pre_id, cid, col, row, sx, sy, item["viz"])

    # ═══════════════════════════════════════════════════════════════════════════
    # 3. 🚀 PIPELINE OPERATIONS & AIRFLOW MONITOR (ETL Infrastructure)
    # ═══════════════════════════════════════════════════════════════════════════
    col_name_3 = "03 - Pipeline Orchestration & SLA Health"
    dash_name_3 = "🚀 Cambodia CPI Pipeline Operations & Monitoring Dashboard"

    print("[3/5] Setting up Collection 03: Pipeline Operations & SLA Health...")
    c_ops = get_or_create_collection(
        cur,
        col_name_3,
        "Live DAG monitoring, incident tracking, source ingestion health, fuel prices, and dimensional fact tables.",
        "#2E5BFF"
    )

    d_ops_id = create_or_update_dashboard(
        cur,
        dash_name_3,
        "Live real-time monitoring of Airflow DAG runs, scraper ingestion progress, failure alerts, and warehouse SLAs.",
        c_ops
    )

    ops_cards = [
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
            "grid": (0, 0, 8, 3)
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
            "grid": (8, 0, 8, 3)
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
            "grid": (16, 0, 8, 3)
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
            "grid": (0, 3, 14, 8)
        },
        {
            "name": "Data Freshness SLA & Lag by Source",
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
        {
            "name": "Daily Store Scraper Ingestion Progress",
            "desc": "Real-time checklist of all 20 retail store scrapers running today.",
            "display": "table",
            "sql": """
                WITH latest_scrape AS (
                    SELECT store_slug, COUNT(*) AS raw_count_today
                    FROM staging.raw_scrapes
                    WHERE scrape_date = (SELECT MAX(scrape_date) FROM staging.raw_scrapes)
                    GROUP BY store_slug
                ),
                dag_states AS (
                    SELECT DISTINCT ON (dag_id)
                        REPLACE(REPLACE(dag_id, 'scrape_', ''), '_dag', '') AS store_key,
                        state,
                        start_date,
                        end_date
                    FROM airflow_monitor.dag_run
                    WHERE DATE(start_date AT TIME ZONE 'Asia/Phnom_Penh') = (SELECT MAX(DATE(start_date AT TIME ZONE 'Asia/Phnom_Penh')) FROM airflow_monitor.dag_run)
                    ORDER BY dag_id, start_date DESC
                )
                SELECT 
                    s.store_slug AS "Store Slug",
                    s.store_name AS "Store Name",
                    s.channel AS "Channel Type",
                    COALESCE(UPPER(d.state), 'PENDING') AS "DAG State",
                    COALESCE(ls.raw_count_today, 0) AS "Raw Records Today",
                    CASE 
                        WHEN COALESCE(ls.raw_count_today, 0) > 0 THEN '✅ INGESTED'
                        WHEN d.state = 'running' THEN '⏳ SCRAPING'
                        WHEN d.state = 'failed' THEN '❌ FAILED'
                        ELSE '⏸️ IDLE / WAITING'
                    END AS "Ingest Status"
                FROM gold.dim_stores s
                LEFT JOIN latest_scrape ls ON ls.store_slug = s.store_slug
                LEFT JOIN dag_states d ON d.store_key = s.store_slug
                ORDER BY "Raw Records Today" DESC;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 11, 24, 8)
        }
    ]

    for item in ops_cards:
        cid = create_or_update_card(cur, item["name"], item["desc"], item["display"], item["sql"], item["viz"], c_ops, db_id=db_id)
        col, row, sx, sy = item["grid"]
        place_card_on_dashboard(cur, d_ops_id, cid, col, row, sx, sy, item["viz"])

    # ═══════════════════════════════════════════════════════════════════════════
    # 4. 🕷️ SCRAPER INGESTION & FIELD EXTRACTION TELEMETRY
    # ═══════════════════════════════════════════════════════════════════════════
    col_name_4 = "04 - Scraper Ingestion & Field Extraction Telemetry"
    dash_name_4 = "🕷️ Scraper Data Health & Extraction Quality Dashboard"

    print("[4/5] Setting up Collection 04: Scraper Extraction Telemetry...")
    c_scrape = get_or_create_collection(
        cur,
        col_name_4,
        "Comprehensive scrape ingestion volume, field extraction completeness, fallback rates, and 30-day ingestion trends.",
        "#509EE3"
    )

    d_scrape_id = create_or_update_dashboard(
        cur,
        dash_name_4,
        "Telemetry for web scrapers: volume stability, field completeness matrix, and selector fallback rates.",
        c_scrape
    )

    scrape_cards = [
        {
            "name": "Scraper Ingestion Success Rate (%)",
            "desc": "Percentage of 20 scrapers that successfully delivered data today.",
            "display": "scalar",
            "sql": """
                SELECT 
                    ROUND((COUNT(DISTINCT store_slug) * 100.0 / 20.0)::numeric, 1) AS "Scraper Success Rate (%)"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices);
            """,
            "viz": {},
            "grid": (0, 0, 8, 3)
        },
        {
            "name": "Active Store Channels Ingested",
            "desc": "Distinct active retail store channels successfully ingested on the latest scrape date.",
            "display": "scalar",
            "sql": """
                SELECT COUNT(DISTINCT store_slug) AS "Active Stores Today"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices);
            """,
            "viz": {},
            "grid": (8, 0, 8, 3)
        },
        {
            "name": "Selector Fallback Rate (%)",
            "desc": "Percentage of items extracted using fallback selectors (potential website HTML structure change).",
            "display": "scalar",
            "sql": """
                SELECT 
                    ROUND((COUNT(*) FILTER (WHERE is_fallback = TRUE) * 100.0 / NULLIF(COUNT(*), 0))::numeric, 2) AS "Fallback Rate (%)"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices);
            """,
            "viz": {},
            "grid": (16, 0, 8, 3)
        },
        {
            "name": "Daily Scraped Observation Volume by Store (Last 30 Days)",
            "desc": "Stacked daily scrape observation volume per store channel over the last 30 days.",
            "display": "bar",
            "sql": """
                SELECT 
                    scrape_date AS "Scrape Date",
                    store_slug AS "Store",
                    COUNT(*) AS "Records Scraped"
                FROM silver.clean_store_prices
                WHERE scrape_date >= (SELECT MAX(scrape_date) - INTERVAL '30 days' FROM silver.clean_store_prices)
                GROUP BY scrape_date, store_slug
                ORDER BY scrape_date ASC, "Records Scraped" DESC;
            """,
            "viz": {
                "graph.dimensions": ["Scrape Date", "Store"],
                "graph.metrics": ["Records Scraped"],
                "stackable.stack_type": "stacked"
            },
            "grid": (0, 3, 24, 8)
        },
        {
            "name": "Store Scrape Ingestion Matrix (Last 14 Days)",
            "desc": "Detailed daily volume matrix for each store channel across the last 14 calendar days.",
            "display": "table",
            "sql": """
                WITH date_bounds AS (
                    SELECT MAX(scrape_date) AS max_d FROM silver.clean_store_prices
                )
                SELECT 
                    store_slug AS "Store Slug",
                    COUNT(*) FILTER (WHERE scrape_date = max_d) AS "Latest",
                    COUNT(*) FILTER (WHERE scrape_date = max_d - INTERVAL '1 day') AS "D-1",
                    COUNT(*) FILTER (WHERE scrape_date = max_d - INTERVAL '2 days') AS "D-2",
                    COUNT(*) FILTER (WHERE scrape_date = max_d - INTERVAL '3 days') AS "D-3",
                    COUNT(*) FILTER (WHERE scrape_date = max_d - INTERVAL '4 days') AS "D-4",
                    COUNT(*) FILTER (WHERE scrape_date = max_d - INTERVAL '5 days') AS "D-5",
                    COUNT(*) FILTER (WHERE scrape_date = max_d - INTERVAL '6 days') AS "D-6",
                    COUNT(*) AS "Total 14D Records"
                FROM silver.clean_store_prices, date_bounds
                WHERE scrape_date >= max_d - INTERVAL '14 days'
                GROUP BY store_slug
                ORDER BY "Latest" DESC;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 11, 12, 8)
        },
        {
            "name": "Scraper Field Extraction Completeness (%)",
            "desc": "Completeness audit of barcode, brand, category, size unit, and promo rates per store.",
            "display": "table",
            "sql": """
                SELECT 
                    store_slug AS "Store",
                    COUNT(*) AS "Total Items",
                    ROUND((COUNT(barcode) FILTER (WHERE barcode IS NOT NULL AND TRIM(barcode) <> '') * 100.0 / COUNT(*))::numeric, 1) AS "Barcode (%)",
                    ROUND((COUNT(brand) FILTER (WHERE brand IS NOT NULL AND TRIM(brand) <> '') * 100.0 / COUNT(*))::numeric, 1) AS "Brand (%)",
                    ROUND((COUNT(category_native) FILTER (WHERE category_native IS NOT NULL AND TRIM(category_native) <> '') * 100.0 / COUNT(*))::numeric, 1) AS "Category Native (%)",
                    ROUND((COUNT(size_unit) FILTER (WHERE size_unit IS NOT NULL AND TRIM(size_unit) <> '') * 100.0 / COUNT(*))::numeric, 1) AS "Unit Size (%)",
                    ROUND((COUNT(*) FILTER (WHERE discount_pct IS NOT NULL AND discount_pct > 0) * 100.0 / COUNT(*))::numeric, 1) AS "Promo Rate (%)"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices)
                GROUP BY store_slug
                ORDER BY "Total Items" DESC;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (12, 11, 12, 8)
        }
    ]

    for item in scrape_cards:
        cid = create_or_update_card(cur, item["name"], item["desc"], item["display"], item["sql"], item["viz"], c_scrape, db_id=db_id)
        col, row, sx, sy = item["grid"]
        place_card_on_dashboard(cur, d_scrape_id, cid, col, row, sx, sy, item["viz"])

    # ═══════════════════════════════════════════════════════════════════════════
    # 5. 🏷️ SILVER CLASSIFICATION & REVIEW QUEUE (AI & Human QA)
    # ═══════════════════════════════════════════════════════════════════════════
    col_name_5 = "05 - Silver Classification & Review Queue"
    dash_name_5 = "🏷️ Silver Classification & Human Review Dashboard"

    print("[5/5] Setting up Collection 05: Silver Classification & Review Queue...")
    c_class = get_or_create_collection(
        cur,
        col_name_5,
        "AI COICOP classification distribution, matching method breakdown, price outlier investigation, and fuzzy matching review queues.",
        "#9B59B6"
    )

    d_class_id = create_or_update_dashboard(
        cur,
        dash_name_5,
        "Silver layer classification intelligence: method breakdown, division distribution, and human-in-the-loop review queue.",
        c_class
    )

    class_cards = [
        {
            "name": "Cleaned Products in Silver",
            "desc": "Unique distinct canonical items matched and cleaned in the Silver layer today.",
            "display": "scalar",
            "sql": """
                SELECT COUNT(*) AS "Cleaned Products in Silver"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices);
            """,
            "viz": {},
            "grid": (0, 0, 6, 3)
        },
        {
            "name": "COICOP Classification Coverage (%)",
            "desc": "Percentage of items successfully classified into a valid COICOP division.",
            "display": "scalar",
            "sql": """
                SELECT 
                    ROUND((COUNT(*) FILTER (WHERE coicop_division IS NOT NULL AND coicop_division <> 'UNCLASSIFIED') * 100.0 / NULLIF(COUNT(*), 0))::numeric, 2) AS "Classification Coverage (%)"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices);
            """,
            "viz": {},
            "grid": (6, 0, 6, 3)
        },
        {
            "name": "Direct Resolution Share (Exact/Domain)",
            "desc": "Percentage of items matched directly without needing AI review.",
            "display": "scalar",
            "sql": """
                SELECT 
                    ROUND((COUNT(*) FILTER (WHERE match_method IN ('barcode_exact', 'sku_exact', 'exact_text')) * 100.0 / NULLIF(COUNT(*), 0))::numeric, 1) AS "Direct Exact Match (%)"
                FROM silver.item_match_log;
            """,
            "viz": {},
            "grid": (12, 0, 6, 3)
        },
        {
            "name": "Pending Human Review Queue",
            "desc": "Count of ambiguous fuzzy matched items currently awaiting review.",
            "display": "scalar",
            "sql": """
                SELECT COUNT(*) AS "Pending Review Items"
                FROM silver.needs_review
                WHERE status = 'pending';
            """,
            "viz": {},
            "grid": (18, 0, 6, 3)
        },
        {
            "name": "COICOP 12-Division Product Distribution",
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
            "grid": (0, 3, 8, 8)
        },
        {
            "name": "Item Matching Method Distribution",
            "desc": "Breakdown of entity resolution methods: Barcode, SKU, Exact Text, Vector Cosine, New Item.",
            "display": "bar",
            "sql": """
                SELECT 
                    COALESCE(match_method, 'unknown') AS "Matching Method",
                    COUNT(*) AS "Matched Count"
                FROM silver.item_match_log
                GROUP BY match_method
                ORDER BY "Matched Count" DESC;
            """,
            "viz": {
                "graph.dimensions": ["Matching Method"],
                "graph.metrics": ["Matched Count"]
            },
            "grid": (8, 3, 8, 8)
        },
        {
            "name": "COICOP Classification Method Breakdown",
            "desc": "Distribution of classification methods: Gemini AI, manual override, barcode, or category mapping.",
            "display": "bar",
            "sql": """
                SELECT 
                    COALESCE(coicop_method, 'unknown') AS "Classification Method",
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
            "grid": (16, 3, 8, 8)
        },
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
            "grid": (0, 11, 14, 8)
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
            "grid": (14, 11, 10, 8)
        }
    ]

    for item in class_cards:
        cid = create_or_update_card(cur, item["name"], item["desc"], item["display"], item["sql"], item["viz"], c_class, db_id=db_id)
        col, row, sx, sy = item["grid"]
        place_card_on_dashboard(cur, d_class_id, cid, col, row, sx, sy, item["viz"])

    cur.execute("DELETE FROM query_cache;")
    conn.commit()
    conn.close()

    print("\n=============================================================================")
    print("SUCCESS: 5 Deduplicated Metabase Dashboards fully provisioned!")
    print(f"  [1] Macro CPI Inflation Dashboard ID: {d_cpi_id} | Collection: {col_name_1}")
    print(f"  [2] Pre-CPI Econometric Screener ID: {d_pre_id} | Collection: {col_name_2}")
    print(f"  [3] Pipeline Operations Dashboard ID: {d_ops_id} | Collection: {col_name_3}")
    print(f"  [4] Scraper Extraction Telemetry ID: {d_scrape_id} | Collection: {col_name_4}")
    print(f"  [5] Silver Classification Queue ID: {d_class_id} | Collection: {col_name_5}")
    print("  Metabase URL: http://localhost:3001 (or :3000)")
    print("=============================================================================")

if __name__ == "__main__":
    provision_all()
