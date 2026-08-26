"""
=============================================================================
METABASE CLEANUP & RE-ALIGNMENT SCRIPT
Removes all orphaned dashboards and provisions 2 clean, fast dashboards:
  1. 01 - Cambodia Daily CPI & Inflation Analytics
  2. 02 - Cambodia CPI Pipeline Monitoring & Data Explorer
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

def get_db_connection(dbname):
    if dbname == "metabase":
        return psycopg2.connect("postgresql://metabase:metabase@localhost:5432/metabase")
    return psycopg2.connect("postgresql://cpi_user:cpi_pass@localhost:5432/cpi_db")

def cleanup_and_rebuild():
    conn = get_db_connection("metabase")
    cur = conn.cursor()

    print("Step 1: Purging all old dashboards, dashboard cards, and custom collections...")
    # Delete all dashboard cards
    cur.execute("DELETE FROM report_dashboardcard;")
    cur.execute("DELETE FROM report_dashboard;")
    cur.execute("DELETE FROM report_card;")
    cur.execute("DELETE FROM collection WHERE id > 1;") # Preserve root/personal collection
    cur.execute("DELETE FROM query_cache;")
    conn.commit()

    db_id = 2 # cpi_db
    now = datetime.now(timezone.utc)

    # -------------------------------------------------------------------------
    # Collection 1: CPI Analytics
    # -------------------------------------------------------------------------
    print("Step 2: Creating Collection '01 - Cambodia Daily CPI & Inflation Analytics'...")
    cur.execute("""
        INSERT INTO collection (name, description, slug, entity_id, location, archived, created_at, type)
        VALUES ('01 - Cambodia Daily CPI & Inflation Analytics', 'Executive CPI inflation indicators, Jevons micro-indices, and 12-division COICOP performance', '01-cpi-analytics', %s, '/', false, %s, 'default')
        RETURNING id;
    """, (generate_entity_id(), now))
    c_cpi = cur.fetchone()[0]

    cur.execute("""
        INSERT INTO report_dashboard (created_at, updated_at, name, description, creator_id, parameters, archived, collection_id, width, entity_id, auto_apply_filters)
        VALUES (%s, %s, 'Cambodia Daily Consumer Price Index (CPI) Dashboard', 'Daily Consumer Price Index tracking headline inflation, core inflation, and 12-division COICOP movements across Cambodia.', 1, '[]', false, %s, 'fixed', %s, true)
        RETURNING id;
    """, (now, now, c_cpi, generate_entity_id()))
    d_cpi = cur.fetchone()[0]

    # -------------------------------------------------------------------------
    # Collection 2: Operations Monitoring
    # -------------------------------------------------------------------------
    print("Step 3: Creating Collection '02 - Cambodia CPI Pipeline Monitoring & Data Explorer'...")
    cur.execute("""
        INSERT INTO collection (name, description, slug, entity_id, location, archived, created_at, type)
        VALUES ('02 - Cambodia CPI Pipeline Monitoring & Data Explorer', 'Real-time DAG execution, 20-source scraper health, FX rates, and price alerts', '02-pipeline-monitoring', %s, '/', false, %s, 'default')
        RETURNING id;
    """, (generate_entity_id(), now))
    c_ops = cur.fetchone()[0]

    cur.execute("""
        INSERT INTO report_dashboard (created_at, updated_at, name, description, creator_id, parameters, archived, collection_id, width, entity_id, auto_apply_filters)
        VALUES (%s, %s, 'Cambodia CPI Pipeline Operations & Monitoring Dashboard', 'Live real-time monitoring of Airflow DAG runs, scraper ingestion progress, failure alerts, and data volume.', 1, '[]', false, %s, 'fixed', %s, true)
        RETURNING id;
    """, (now, now, c_ops, generate_entity_id()))
    d_ops = cur.fetchone()[0]

    # Helper function to insert card and place on dashboard
    def add_card(dash_id, col_id, name, desc, display, sql, viz, col, row, sx, sy):
        dataset_query = {
            "database": db_id,
            "type": "native",
            "native": {
                "query": sql.strip(),
                "template-tags": {}
            }
        }
        cur.execute("""
            INSERT INTO report_card (
                created_at, updated_at, name, description, display, dataset_query,
                visualization_settings, creator_id, database_id, query_type, archived,
                collection_id, enable_embedding, dataset, entity_id, collection_preview, type
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, 1, %s, 'native', false, %s, false, false, %s, true, 'question')
            RETURNING id;
        """, (now, now, name, desc, display, json.dumps(dataset_query), json.dumps(viz), db_id, col_id, generate_entity_id()))
        cid = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO report_dashboardcard (
                created_at, updated_at, dashboard_id, card_id, row, col,
                size_x, size_y, parameter_mappings, visualization_settings, entity_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '[]', %s, %s);
        """, (now, now, dash_id, cid, row, col, sx, sy, json.dumps(viz), generate_entity_id()))

    # -------------------------------------------------------------------------
    # Cards for CPI Dashboard
    # -------------------------------------------------------------------------
    print("Step 4: Provisioning CPI Dashboard Cards...")
    add_card(
        d_cpi, c_cpi,
        "Current Headline Daily CPI (Base 100 = Aug 18, 2026)",
        "Latest daily headline consumer price index weighted across all 12 UN COICOP divisions.",
        "scalar",
        """
        SELECT ROUND(headline_cpi::numeric, 2) AS "Headline CPI (Base 100)"
        FROM gold.fct_cpi_daily
        WHERE calculation_date = (SELECT MAX(calculation_date) FROM gold.fct_cpi_daily)
        LIMIT 1;
        """,
        {},
        0, 0, 8, 3
    )

    add_card(
        d_cpi, c_cpi,
        "Core CPI (Excluding Food & Energy)",
        "Underlying inflation measure excluding volatile Food and Transport fuel components.",
        "scalar",
        """
        SELECT ROUND(core_cpi::numeric, 2) AS "Core CPI (Ex-Food & Energy)"
        FROM gold.fct_cpi_daily
        WHERE calculation_date = (SELECT MAX(calculation_date) FROM gold.fct_cpi_daily)
        LIMIT 1;
        """,
        {},
        8, 0, 8, 3
    )

    add_card(
        d_cpi, c_cpi,
        "Active Basket Items Tracked Daily",
        "Number of canonical consumer products evaluated with Jevons micro-indices.",
        "scalar",
        """
        SELECT COUNT(DISTINCT item_id) AS "Active Basket Items"
        FROM gold.fct_elementary_indices
        WHERE calculation_date = (SELECT MAX(calculation_date) FROM gold.fct_elementary_indices);
        """,
        {},
        16, 0, 8, 3
    )

    add_card(
        d_cpi, c_cpi,
        "Daily Headline vs Core CPI Index Trend (Time Series)",
        "Daily index trajectory comparing Headline Inflation vs Core Inflation.",
        "line",
        """
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
        {"graph.dimensions": ["Date"], "graph.metrics": ["Headline CPI", "Core CPI"]},
        0, 3, 24, 8
    )

    add_card(
        d_cpi, c_cpi,
        "12-Division COICOP Expenditure Weights & Index Performance",
        "Detailed breakdown across all 12 UN COICOP divisions with official NIS weights.",
        "table",
        """
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
        {"table.pivot_column": None},
        0, 11, 14, 8
    )

    add_card(
        d_cpi, c_cpi,
        "Top Basket Price Movers (Largest Price Changes)",
        "Staple consumer goods exhibiting significant price shifts vs base period.",
        "table",
        """
        SELECT 
            c.canonical_name AS "Product Name",
            e.coicop_division AS "Div",
            ROUND(e.base_price_khr, 0) AS "Base Price (KHR)",
            ROUND(e.current_price_khr, 0) AS "Current Price (KHR)",
            ROUND((e.price_ratio - 1.0) * 100.0, 1) AS "Price Change (%)",
            CASE WHEN e.is_imputed THEN 'Imputed' ELSE 'Observed' END AS "Method"
        FROM gold.fct_elementary_indices e
        JOIN silver.canonical_items c ON c.item_id = e.item_id
        WHERE e.calculation_date = (SELECT MAX(calculation_date) FROM gold.fct_elementary_indices)
        ORDER BY ABS(e.price_ratio - 1.0) DESC
        LIMIT 20;
        """,
        {"table.pivot_column": None},
        14, 11, 10, 8
    )

    # -------------------------------------------------------------------------
    # Cards for Operations Dashboard
    # -------------------------------------------------------------------------
    print("Step 5: Provisioning Operations Dashboard Cards...")
    add_card(
        d_ops, c_ops,
        "DAGs Running In-Flight Now",
        "Count of Airflow DAGs currently actively executing right now.",
        "scalar",
        """
        SELECT COUNT(*) AS "DAGs Running Now"
        FROM airflow_monitor.dag_run
        WHERE state = 'running'
          AND DATE(start_date AT TIME ZONE 'Asia/Phnom_Penh') = (SELECT MAX(DATE(start_date AT TIME ZONE 'Asia/Phnom_Penh')) FROM airflow_monitor.dag_run);
        """,
        {},
        0, 0, 4, 3
    )

    add_card(
        d_ops, c_ops,
        "Failed DAGs / Tasks Today",
        "Count of active DAGs currently in failed state.",
        "scalar",
        """
        WITH latest_runs AS (
            SELECT DISTINCT ON (dag_id) dag_id, state, start_date
            FROM airflow_monitor.dag_run
            WHERE DATE(start_date AT TIME ZONE 'Asia/Phnom_Penh') = (SELECT MAX(DATE(start_date AT TIME ZONE 'Asia/Phnom_Penh')) FROM airflow_monitor.dag_run)
            ORDER BY dag_id, start_date DESC
        )
        SELECT COUNT(*) AS "Failed DAGs Today"
        FROM latest_runs
        WHERE state = 'failed';
        """,
        {},
        4, 0, 5, 3
    )

    add_card(
        d_ops, c_ops,
        "Total Raw Prices Scraped Today (Bronze)",
        "Total raw uncleaned price records collected across all 20 retail scrapers.",
        "scalar",
        """
        SELECT COUNT(*) AS "Raw Prices Scraped Today"
        FROM bronze.raw_prices
        WHERE scraped_at::date = (SELECT MAX(scraped_at::date) FROM bronze.raw_prices);
        """,
        {},
        9, 0, 5, 3
    )

    add_card(
        d_ops, c_ops,
        "Cleaned Products in Silver (Latest)",
        "Unique distinct canonical items matched and cleaned in the Silver layer.",
        "scalar",
        """
        SELECT COUNT(*) AS "Cleaned Products in Silver"
        FROM silver.clean_store_prices
        WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices);
        """,
        {},
        14, 0, 5, 3
    )

    add_card(
        d_ops, c_ops,
        "Official MEF USD/KHR Rate Today",
        "Official daily exchange rate from Ministry of Economy and Finance (MEF API).",
        "scalar",
        """
        SELECT rate AS "USD/KHR Rate Today"
        FROM staging.exchange_rates
        WHERE execution_date = (SELECT MAX(execution_date) FROM staging.exchange_rates);
        """,
        {},
        19, 0, 5, 3
    )

    add_card(
        d_ops, c_ops,
        "Failed DAG Tasks & Ingestion Alerts (Today)",
        "Active failed DAGs requiring attention. If empty, all pipelines ran successfully.",
        "table",
        """
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
        {"table.pivot_column": None},
        0, 3, 11, 7
    )

    add_card(
        d_ops, c_ops,
        "Real-Time Airflow DAG Pipeline Monitor (Today)",
        "Live execution state of all DAGs triggered today (Scrapers, Silver, Master, Gold).",
        "table",
        """
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
        {"table.pivot_column": None},
        11, 3, 13, 7
    )

    add_card(
        d_ops, c_ops,
        "Daily Store Scraper Ingestion Progress",
        "Status and volume of raw scraped data collected today per active retail/market channel.",
        "table",
        """
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
        ORDER BY "Raw Records Today" DESC;
        """,
        {"table.pivot_column": None},
        0, 10, 12, 8
    )

    add_card(
        d_ops, c_ops,
        "Store Ingest Volume: Latest Day vs Previous Day",
        "Comparison of ingested product count per store between latest day and previous day.",
        "table",
        """
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
        {"table.pivot_column": None},
        12, 10, 12, 8
    )

    add_card(
        d_ops, c_ops,
        "All Gasoline & Retail Fuel Prices (Latest)",
        "Live prices of Gasoline (EA92, EA95), Diesel, and Petroleum products collected.",
        "table",
        """
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
        {"table.pivot_column": None},
        0, 18, 24, 6
    )

    conn.commit()
    conn.close()

    print("\n=============================================================================")
    print("SUCCESS: Metabase Dashboards Rebuilt Cleanly!")
    print(f"  [1] CPI Inflation Dashboard ID: {d_cpi} | Collection: {c_cpi}")
    print(f"  [2] Operations Dashboard ID: {d_ops} | Collection: {c_ops}")
    print("  Metabase URL: http://localhost:3000")
    print("=============================================================================")

if __name__ == "__main__":
    cleanup_and_rebuild()
