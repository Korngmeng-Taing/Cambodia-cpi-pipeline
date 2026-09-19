"""
=============================================================================
CAMBODIA CPI PIPELINE — CONSOLIDATED 3 METABASE DASHBOARDS PROVISIONER
Provisions:
  1. 01 - Macro CPI & Inflation Analytics
  2. 02 - Operations & 25-Source Telemetry
  3. 03 - Silver Data Quality Screener
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

def create_or_update_card(cur, name, description, display, query_sql, viz_settings, collection_id, db_id=2, creator_id=1, template_tags=None):
    dataset_query = {
        "database": db_id,
        "type": "native",
        "native": {
            "query": query_sql.strip(),
            "template-tags": template_tags or {}
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

def create_or_update_dashboard(cur, name, description, collection_id, creator_id=1, parameters=None):
    now = datetime.now(timezone.utc)
    params_json = json.dumps(parameters or [])
    cur.execute("SELECT id FROM report_dashboard WHERE name = %s AND collection_id = %s AND archived = false", (name, collection_id))
    row = cur.fetchone()
    if row:
        dash_id = row[0]
        cur.execute("""
            UPDATE report_dashboard 
            SET description = %s, parameters = %s, updated_at = %s
            WHERE id = %s;
        """, (description, params_json, now, dash_id))
        return dash_id
    else:
        entity_id = generate_entity_id()
        cur.execute("""
            INSERT INTO report_dashboard (
                created_at, updated_at, name, description, creator_id,
                parameters, archived, collection_id, width, enable_embedding,
                entity_id, collection_position, auto_apply_filters
            )
            VALUES (%s, %s, %s, %s, %s, %s, false, %s, 'fixed', false, %s, 1, true)
            RETURNING id;
        """, (now, now, name, description, creator_id, params_json, collection_id, entity_id))
        return cur.fetchone()[0]

def place_card_on_dashboard(cur, dashboard_id, card_id, col, row, size_x, size_y, viz_settings, parameter_mappings=None):
    cur.execute("""
        SELECT id FROM report_dashboardcard 
        WHERE dashboard_id = %s AND card_id = %s;
    """, (dashboard_id, card_id))
    r = cur.fetchone()
    now = datetime.now(timezone.utc)
    entity_id = generate_entity_id()
    mappings_json = json.dumps(parameter_mappings or [])
    if r:
        cur.execute("""
            UPDATE report_dashboardcard
            SET col = %s, row = %s, size_x = %s, size_y = %s, visualization_settings = %s, parameter_mappings = %s, updated_at = %s
            WHERE id = %s;
        """, (col, row, size_x, size_y, json.dumps(viz_settings), mappings_json, now, r[0]))
    else:
        cur.execute("""
            INSERT INTO report_dashboardcard (
                created_at, updated_at, dashboard_id, card_id, row, col,
                size_x, size_y, parameter_mappings, visualization_settings, entity_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """, (now, now, dashboard_id, card_id, row, col, size_x, size_y, mappings_json, json.dumps(viz_settings), entity_id))

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
    # 1. 🇰🇭 DASHBOARD 1: MACRO CPI & INFLATION ANALYTICS (Executive BI)
    # ═══════════════════════════════════════════════════════════════════════════
    col_name_1 = "01 - Macro CPI & Inflation Analytics"
    dash_name_1 = "🇰🇭 Macro CPI & Inflation Analytics"

    print("[1/3] Setting up Collection 01: Macro CPI & Inflation Analytics...")
    c_cpi = get_or_create_collection(
        cur,
        col_name_1,
        "Official macroeconomic inflation indicators, Headline vs Core CPI, 12-division COICOP performance, and Nowcast projections.",
        "#008080"
    )

    dash_1_params = [
        {
            "id": "param_div",
            "name": "COICOP Division",
            "slug": "coicop_division",
            "type": "category",
            "sectionId": "string"
        }
    ]

    d_cpi_id = create_or_update_dashboard(
        cur,
        dash_name_1,
        "Executive inflation overview: Daily and Monthly Headline CPI, Core CPI, 12-division COICOP index matrix, 4-digit class drill-down, weighted contributors, and Month-End Nowcasting.",
        c_cpi,
        parameters=dash_1_params
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
                [[ AND coicop_division = {{coicop_division}} ]]
                ORDER BY coicop_division ASC;
            """,
            "viz": {"table.pivot_column": None},
            "template_tags": {
                "coicop_division": {
                    "id": "tt_cpi_matrix_div",
                    "name": "coicop_division",
                    "display-name": "COICOP Division",
                    "type": "text"
                }
            },
            "mappings": [
                {
                    "parameter_id": "param_div",
                    "target": ["variable", ["template-tag", "coicop_division"]]
                }
            ],
            "grid": (0, 11, 12, 8)
        },
        {
            "name": "4-Digit COICOP Class Breakdown & MoM Rates",
            "desc": "Detailed 4-digit subclass index movements (e.g. Bread & Cereals, Meat, Fuel, Electricity) showing granular inflationary pressure.",
            "display": "table",
            "sql": """
                SELECT 
                    c.coicop_code AS "Class Code",
                    COALESCE(w.coicop_name, c.coicop_code) AS "Class Name",
                    COALESCE(w.coicop_name_kh, '') AS "ឈ្មោះជាភាសាខ្មែរ",
                    c.coicop_division AS "Div",
                    ROUND(COALESCE(w.weight_pct, 0.0), 3) AS "Weight (%)",
                    c.class_index AS "Class Index",
                    c.dod_class_change_pct AS "DoD Change (%)",
                    c.item_count AS "Active Items",
                    c.imputed_item_count AS "Imputed Items"
                FROM gold.v_coicop_class_breakdown c
                LEFT JOIN gold.cambodia_cpi_coicop_weights_breakdown w ON w.coicop_code = c.coicop_code
                WHERE c.calculation_date = (SELECT MAX(calculation_date) FROM gold.v_coicop_class_breakdown)
                [[ AND c.coicop_division = {{coicop_division}} ]]
                ORDER BY COALESCE(w.weight_pct, 0.0) DESC, c.coicop_code ASC;
            """,
            "viz": {"table.pivot_column": None},
            "template_tags": {
                "coicop_division": {
                    "id": "tt_class_breakdown_div",
                    "name": "coicop_division",
                    "display-name": "COICOP Division",
                    "type": "text"
                }
            },
            "mappings": [
                {
                    "parameter_id": "param_div",
                    "target": ["variable", ["template-tag", "coicop_division"]]
                }
            ],
            "grid": (12, 11, 12, 8)
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
                JOIN silver.canonical_items i ON i.item_id = e.item_id::uuid
                WHERE e.calculation_date = (SELECT MAX(calculation_date) FROM gold.fct_elementary_indices)
                [[ AND e.coicop_division = {{coicop_division}} ]]
                ORDER BY ABS(e.price_ratio - 1.0) DESC
                LIMIT 20;
            """,
            "viz": {"table.pivot_column": None},
            "template_tags": {
                "coicop_division": {
                    "id": "tt_movers_div",
                    "name": "coicop_division",
                    "display-name": "COICOP Division",
                    "type": "text"
                }
            },
            "mappings": [
                {
                    "parameter_id": "param_div",
                    "target": ["variable", ["template-tag", "coicop_division"]]
                }
            ],
            "grid": (0, 19, 12, 8)
        },
        {
            "name": "Top Weighted Inflation Contributors (CPI Impact)",
            "desc": "Top individual basket products driving national inflation ranked by true weighted impact on Headline CPI (wi * dPi).",
            "display": "table",
            "sql": """
                WITH latest_date AS (
                    SELECT MAX(calculation_date) AS max_date FROM gold.fct_elementary_indices
                ),
                div_counts AS (
                    SELECT coicop_division, COUNT(*) AS cnt
                    FROM gold.fct_elementary_indices, latest_date
                    WHERE calculation_date = latest_date.max_date
                    GROUP BY coicop_division
                )
                SELECT 
                    i.canonical_name AS "Product Name",
                    e.coicop_division AS "Div",
                    w.division_name AS "COICOP Division",
                    ROUND(e.current_price_khr, 0) AS "Current Price (KHR)",
                    ROUND((e.price_ratio - 1.0) * 100.0, 1) AS "Price Change (%)",
                    ROUND(((e.price_ratio - 1.0) * (w.weight_pct / NULLIF(dc.cnt, 0)))::numeric, 4) AS "CPI Contribution (pp)",
                    CASE 
                        WHEN ((e.price_ratio - 1.0) * (w.weight_pct / NULLIF(dc.cnt, 0))) > 0 THEN '📈 UPWARD PRESSURE'
                        WHEN ((e.price_ratio - 1.0) * (w.weight_pct / NULLIF(dc.cnt, 0))) < 0 THEN '📉 DOWNWARD DRAG'
                        ELSE '⚖️ NEUTRAL'
                    END AS "Inflation Pressure"
                FROM gold.fct_elementary_indices e
                CROSS JOIN latest_date ld
                JOIN silver.canonical_items i ON i.item_id = e.item_id::uuid
                JOIN gold.coicop_weights w ON w.coicop_division = e.coicop_division
                JOIN div_counts dc ON dc.coicop_division = e.coicop_division
                WHERE e.calculation_date = ld.max_date
                [[ AND e.coicop_division = {{coicop_division}} ]]
                ORDER BY ABS((e.price_ratio - 1.0) * (w.weight_pct / NULLIF(dc.cnt, 0))) DESC
                LIMIT 25;
            """,
            "viz": {"table.pivot_column": None},
            "template_tags": {
                "coicop_division": {
                    "id": "tt_weighted_contrib_div",
                    "name": "coicop_division",
                    "display-name": "COICOP Division",
                    "type": "text"
                }
            },
            "mappings": [
                {
                    "parameter_id": "param_div",
                    "target": ["variable", ["template-tag", "coicop_division"]]
                }
            ],
            "grid": (12, 19, 12, 8)
        },
        {
            "name": "Official UN COICOP 2018 Expenditure Weight Breakdown",
            "desc": "Official NIS Cambodia expenditure basket breakdown across 12 Divisions, 29 Groups, and 48 Classes.",
            "display": "table",
            "sql": """
                SELECT 
                    coicop_level AS "Level",
                    coicop_code AS "COICOP Code",
                    coicop_name AS "Category Name",
                    coicop_name_kh AS "ឈ្មោះជាភាសាខ្មែរ",
                    ROUND(weight_pct, 3) AS "Basket Weight (%)",
                    parent_division AS "Division"
                FROM gold.cambodia_cpi_coicop_weights_breakdown
                WHERE coicop_level <> 'Summary'
                [[ AND parent_division = {{coicop_division}} ]]
                ORDER BY coicop_code ASC;
            """,
            "viz": {"table.pivot_column": None},
            "template_tags": {
                "coicop_division": {
                    "id": "tt_weights_div",
                    "name": "coicop_division",
                    "display-name": "COICOP Division",
                    "type": "text"
                }
            },
            "mappings": [
                {
                    "parameter_id": "param_div",
                    "target": ["variable", ["template-tag", "coicop_division"]]
                }
            ],
            "grid": (0, 27, 24, 8)
        },
        {
            "name": "Current Month Inflation Nowcast (MoM %)",
            "desc": "Real-time daily Month-to-Date inflation nowcast estimating current month outcome before official NIS release.",
            "display": "scalar",
            "sql": """
                SELECT 
                    ROUND(projected_mom_pct::numeric, 2) AS "Nowcast MoM Inflation (%)"
                FROM gold.fct_cpi_nowcast
                WHERE nowcast_date = (SELECT MAX(nowcast_date) FROM gold.fct_cpi_nowcast)
                ORDER BY nowcast_date DESC
                LIMIT 1;
            """,
            "viz": {},
            "grid": (0, 35, 8, 3)
        },
        {
            "name": "Chain-Linked Official NIS CPI Estimate",
            "desc": "Estimated current month National Institute of Statistics official index level (Base Oct-Dec 2006 = 100).",
            "display": "scalar",
            "sql": """
                SELECT 
                    ROUND(COALESCE(nowcast_nis_headline_cpi, nowcast_headline_cpi)::numeric, 2) AS "Nowcast NIS CPI (2006=100)"
                FROM gold.fct_cpi_nowcast
                WHERE nowcast_date = (SELECT MAX(nowcast_date) FROM gold.fct_cpi_nowcast)
                ORDER BY nowcast_date DESC
                LIMIT 1;
            """,
            "viz": {},
            "grid": (8, 35, 8, 3)
        },
        {
            "name": "Nowcast Uncertainty & 95% Confidence Interval",
            "desc": "Intra-month observed day progress and dynamic 95% confidence interval bounds.",
            "display": "scalar",
            "sql": """
                SELECT 
                    CONCAT(days_observed, '/', days_in_month, ' Days | 95% CI: [', ROUND(ci_lower_95::numeric, 1), ' - ', ROUND(ci_upper_95::numeric, 1), ']') AS "Nowcast Confidence"
                FROM gold.fct_cpi_nowcast
                WHERE nowcast_date = (SELECT MAX(nowcast_date) FROM gold.fct_cpi_nowcast)
                ORDER BY nowcast_date DESC
                LIMIT 1;
            """,
            "viz": {},
            "grid": (16, 35, 8, 3)
        },
        {
            "name": "Official NIS vs. Pipeline MoM Inflation Tracking (%)",
            "desc": "Tracking comparison between high-frequency scraped CPI MoM inflation rate and official NIS monthly releases.",
            "display": "line",
            "sql": """
                SELECT 
                    cpi_month AS "Month",
                    pipeline_mom_pct AS "Pipeline MoM (%)",
                    nis_mom_pct AS "Official NIS MoM (%)",
                    mom_diff_pct_points AS "Tracking Error (pp)"
                FROM gold.fct_cpi_nis_comparison
                WHERE pipeline_mom_pct IS NOT NULL AND nis_mom_pct IS NOT NULL
                ORDER BY cpi_month ASC;
            """,
            "viz": {
                "graph.dimensions": ["Month"],
                "graph.metrics": ["Pipeline MoM (%)", "Official NIS MoM (%)"]
            },
            "grid": (0, 38, 12, 8)
        },
        {
            "name": "Official NIS 12-Division Benchmark Comparison Table",
            "desc": "Conformed benchmark evaluation table showing rebased headline index, tracking error, and official NIS releases.",
            "display": "table",
            "sql": """
                SELECT 
                    cpi_month AS "Month",
                    pipeline_headline_cpi AS "Pipeline CPI (2026=100)",
                    nis_headline_cpi AS "Official NIS (2006=100)",
                    pipeline_headline_cpi_rebased_to_nis AS "Pipeline Rebased",
                    headline_rebased_error AS "Rebased Error",
                    pipeline_mom_pct AS "Pipeline MoM (%)",
                    nis_mom_pct AS "NIS MoM (%)",
                    mom_diff_pct_points AS "MoM Diff (pp)",
                    directional_concordance AS "Direction Concordant?",
                    nis_release_date AS "Release Date"
                FROM gold.fct_cpi_nis_comparison
                ORDER BY cpi_month DESC;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (12, 38, 12, 8)
        },
        {
            "name": "5-Basket Nowcast Trajectory & MoM Inflation (%)",
            "desc": "Real-time month-over-month inflation nowcasts across 5 major consumer baskets covering 81.58% of Cambodia's CPI.",
            "display": "line",
            "sql": """
                SELECT 
                    nowcast_date AS "Nowcast Date",
                    nowcasted_mom_pct AS "Headline MoM (%)",
                    projected_food_mom_pct AS "Food (01) MoM (%)",
                    projected_transport_mom_pct AS "Transport (07) MoM (%)",
                    projected_housing_mom_pct AS "Housing/Energy (04) MoM (%)",
                    projected_restaurant_mom_pct AS "Restaurants (11) MoM (%)",
                    projected_alcohol_mom_pct AS "Alcohol (02) MoM (%)"
                FROM gold.v_nowcast_evaluation
                WHERE model_name = 'hybrid_ridge_5basket_v1'
                ORDER BY nowcast_date ASC;
            """,
            "viz": {
                "graph.dimensions": ["Nowcast Date"],
                "graph.metrics": [
                    "Headline MoM (%)",
                    "Food (01) MoM (%)",
                    "Transport (07) MoM (%)",
                    "Housing/Energy (04) MoM (%)",
                    "Restaurants (11) MoM (%)",
                    "Alcohol (02) MoM (%)"
                ]
            },
            "grid": (0, 46, 14, 8)
        },
        {
            "name": "5-Basket Price Relatives & Contribution Breakdown",
            "desc": "Axiomatic Laspeyres price relatives and basket index levels for current month nowcast.",
            "display": "table",
            "sql": """
                SELECT 
                    nowcast_date AS "Date",
                    ROUND(nowcast_headline_cpi::numeric, 2) AS "Headline",
                    ROUND(nowcast_food_cpi::numeric, 2) AS "Food (44.8%)",
                    ROUND(nowcast_transport_cpi::numeric, 2) AS "Transport (12.2%)",
                    ROUND(nowcast_housing_cpi::numeric, 2) AS "Housing (17.1%)",
                    ROUND(nowcast_restaurant_cpi::numeric, 2) AS "Restaurants (5.9%)",
                    ROUND(nowcast_alcohol_cpi::numeric, 2) AS "Alcohol (1.6%)",
                    CONCAT(ROUND(ci_lower_95::numeric, 2), ' - ', ROUND(ci_upper_95::numeric, 2)) AS "95% CI"
                FROM gold.v_nowcast_evaluation
                WHERE model_name = 'hybrid_ridge_5basket_v1'
                ORDER BY nowcast_date DESC
                LIMIT 15;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (14, 46, 10, 8)
        },
        {
            "name": "ML Nowcaster Rolling 3-Month Error Trend (RMSE & MAE)",
            "desc": "Continuous tracking of nowcaster forecast error against official statistical releases across rolling quarters.",
            "display": "line",
            "sql": """
                SELECT 
                    target_month AS "Target Month",
                    rolling_rmse_3m AS "Rolling RMSE (3M)",
                    rolling_mae_3m AS "Rolling MAE (3M)"
                FROM gold.nowcast_performance_metrics
                WHERE rolling_rmse_3m IS NOT NULL
                ORDER BY target_month ASC;
            """,
            "viz": {
                "graph.dimensions": ["Target Month"],
                "graph.metrics": ["Rolling RMSE (3M)", "Rolling MAE (3M)"]
            },
            "grid": (0, 54, 12, 7)
        },
        {
            "name": "ML Nowcaster Directional Accuracy Rate (%)",
            "desc": "Percentage of months where the nowcaster accurately predicted the sign/direction of inflation change.",
            "display": "scalar",
            "sql": """
                SELECT 
                    CONCAT(ROUND((COUNT(CASE WHEN directional_hit THEN 1 END)::numeric / NULLIF(COUNT(*), 0)) * 100.0, 1), '%') AS "Directional Hit Rate"
                FROM gold.nowcast_performance_metrics
                WHERE directional_hit IS NOT NULL;
            """,
            "viz": {},
            "grid": (12, 54, 4, 7)
        },
        {
            "name": "ML Nowcaster Point-in-Time Error Audit Table",
            "desc": "Detailed point-in-time forecast accuracy audit evaluating nowcasts against official monthly inflation releases.",
            "display": "table",
            "sql": """
                SELECT 
                    evaluation_date AS "Eval Date",
                    target_month AS "Month",
                    days_observed AS "Days Obs",
                    nowcast_mom_pct AS "Nowcast MoM (%)",
                    actual_mom_pct AS "Official MoM (%)",
                    mom_error AS "MoM Diff (pp)",
                    cpi_absolute_error AS "Abs Error",
                    cpi_pct_error AS "Error (%)",
                    directional_hit AS "Direction Hit?"
                FROM gold.nowcast_performance_metrics
                ORDER BY evaluation_date DESC, days_observed DESC;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (16, 54, 8, 7)
        },
        {
            "name": "36-Month Calibrated 5-Basket Ridge Elasticities",
            "desc": "Empirical pass-through elasticities (beta) estimated via 36-month expanding RidgeCV across 5 core consumer baskets.",
            "display": "table",
            "sql": """
                SELECT 
                    sample_months AS "Sample Months",
                    ROUND(alpha_drift::numeric, 6) AS "Alpha Drift",
                    ROUND(lambda_penalty::numeric, 4) AS "Optimal Lambda",
                    ROUND(beta_food::numeric, 4) AS "Food (01)",
                    ROUND(beta_transport::numeric, 4) AS "Transport (07)",
                    ROUND(beta_restaurant::numeric, 4) AS "Restaurants (11)",
                    ROUND(beta_housing::numeric, 4) AS "Housing (04)",
                    ROUND(beta_alcohol::numeric, 4) AS "Alcohol (02)",
                    ROUND(beta_fx::numeric, 4) AS "FX (USD/KHR)",
                    ROUND(oos_relative_rmse::numeric, 4) AS "OOS Rel RMSE vs RW"
                FROM gold.nowcast_calibrated_parameters
                ORDER BY calibration_date DESC
                LIMIT 1;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 61, 14, 6)
        },
        {
            "name": "Random Walk Benchmark Scorecard (Relative RMSE)",
            "desc": "Out-of-sample performance scorecard against the canonical Atkeson-Ohanian Random Walk benchmark (score < 1.00 beats benchmark).",
            "display": "scalar",
            "sql": """
                SELECT 
                    CONCAT('Rel RMSE: ', ROUND(oos_relative_rmse::numeric, 4), ' (', ROUND((1.0 - oos_relative_rmse::numeric) * 100.0, 1), '% Beats RW)') AS "Benchmark Scorecard"
                FROM gold.nowcast_calibrated_parameters
                ORDER BY calibration_date DESC
                LIMIT 1;
            """,
            "viz": {},
            "grid": (14, 61, 10, 6)
        }
    ]

    for item in cpi_cards:
        cid = create_or_update_card(
            cur, item["name"], item["desc"], item["display"], item["sql"], item["viz"], c_cpi,
            db_id=db_id, template_tags=item.get("template_tags")
        )
        col, row, sx, sy = item["grid"]
        mappings = []
        for m in item.get("mappings") or []:
            cm = dict(m)
            cm["card_id"] = cid
            mappings.append(cm)
        place_card_on_dashboard(cur, d_cpi_id, cid, col, row, sx, sy, item["viz"], parameter_mappings=mappings)



    # ═══════════════════════════════════════════════════════════════════════════
    # 2. 🚀 DASHBOARD 2: OPERATIONS & 23-SOURCE TELEMETRY
    # ═══════════════════════════════════════════════════════════════════════════
    col_name_2 = "02 - Operations & 25-Source Telemetry"
    dash_name_2 = "02 - Operations & 25-Source Telemetry"

    print("[2/3] Setting up Collection 02: Operations & 25-Source Telemetry...")
    c_ops = get_or_create_collection(
        cur,
        col_name_2,
        "Live pipeline orchestration, DAG monitor, 25 digital store scrapers, SLA lag, volume trends, and extraction completeness.",
        "#2E5BFF"
    )

    dash_2_params = [
        {
            "id": "param_store",
            "name": "Store Selector",
            "slug": "store_slug",
            "type": "category",
            "sectionId": "string"
        }
    ]

    d_ops_id = create_or_update_dashboard(
        cur,
        dash_name_2,
        "Live real-time monitoring of Airflow DAG runs, all 25 store scrapers ingestion progress, failure alerts, and warehouse SLAs.",
        c_ops,
        parameters=dash_2_params
    )

    ops_cards = [
        {
            "name": "Active Stores Ingested Today",
            "desc": "Distinct active retail store channels successfully ingested on the latest scrape date.",
            "display": "scalar",
            "sql": """
                SELECT COUNT(DISTINCT store_slug) AS "Active Stores Today"
                FROM silver.clean_store_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices);
            """,
            "viz": {},
            "grid": (0, 0, 6, 3)
        },
        {
            "name": "Scraper Ingestion Success Rate (%)",
            "desc": "Percentage of active production scrapers that successfully delivered data today.",
            "display": "scalar",
            "sql": """
                WITH target_stores AS (
                    SELECT COUNT(DISTINCT store_slug) AS total_active
                    FROM gold.dim_stores
                    WHERE is_active = TRUE
                )
                SELECT 
                    ROUND((COUNT(DISTINCT c.store_slug) * 100.0 / NULLIF(MAX(t.total_active), 0))::numeric, 1) AS "Scraper Success Rate (%)"
                FROM silver.clean_store_prices c
                CROSS JOIN target_stores t
                WHERE c.scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices);
            """,
            "viz": {},
            "grid": (6, 0, 6, 3)
        },
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
            "grid": (12, 0, 6, 3)
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
            "grid": (18, 0, 6, 3)
        },
        {
            "name": "Daily Store Scraper Ingestion Progress",
            "desc": "Real-time checklist of all 25 active data sources and stores running today.",
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
                WHERE s.is_active = TRUE
                [[ AND s.store_slug = {{store_slug}} ]]
                ORDER BY "Raw Records Today" DESC;
            """,
            "viz": {"table.pivot_column": None},
            "template_tags": {
                "store_slug": {
                    "id": "tt_ops_store_progress",
                    "name": "store_slug",
                    "display-name": "Store Selector",
                    "type": "text"
                }
            },
            "mappings": [
                {
                    "parameter_id": "param_store",
                    "target": ["variable", ["template-tag", "store_slug"]]
                }
            ],
            "grid": (0, 3, 24, 8)
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
            "grid": (0, 11, 14, 8)
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
                WHERE 1=1
                [[ AND source_name = {{store_slug}} ]]
                GROUP BY source_name
                ORDER BY "Lag (Hours)" ASC;
            """,
            "viz": {"table.pivot_column": None},
            "template_tags": {
                "store_slug": {
                    "id": "tt_ops_store_sla",
                    "name": "store_slug",
                    "display-name": "Store Selector",
                    "type": "text"
                }
            },
            "mappings": [
                {
                    "parameter_id": "param_store",
                    "target": ["variable", ["template-tag", "store_slug"]]
                }
            ],
            "grid": (14, 11, 10, 8)
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
                [[ AND store_slug = {{store_slug}} ]]
                GROUP BY scrape_date, store_slug
                ORDER BY scrape_date ASC, "Records Scraped" DESC;
            """,
            "viz": {
                "graph.dimensions": ["Scrape Date", "Store"],
                "graph.metrics": ["Records Scraped"],
                "stackable.stack_type": "stacked"
            },
            "template_tags": {
                "store_slug": {
                    "id": "tt_ops_store_vol",
                    "name": "store_slug",
                    "display-name": "Store Selector",
                    "type": "text"
                }
            },
            "mappings": [
                {
                    "parameter_id": "param_store",
                    "target": ["variable", ["template-tag", "store_slug"]]
                }
            ],
            "grid": (0, 19, 24, 8)
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
                    COALESCE(st.store_name, c.store_slug) AS "Store Name",
                    c.store_slug AS "Store Slug",
                    COUNT(*) FILTER (WHERE c.scrape_date = max_d) AS "Latest",
                    COUNT(*) FILTER (WHERE c.scrape_date = max_d - INTERVAL '1 day') AS "D-1",
                    COUNT(*) FILTER (WHERE c.scrape_date = max_d - INTERVAL '2 days') AS "D-2",
                    COUNT(*) FILTER (WHERE c.scrape_date = max_d - INTERVAL '3 days') AS "D-3",
                    COUNT(*) FILTER (WHERE c.scrape_date = max_d - INTERVAL '4 days') AS "D-4",
                    COUNT(*) FILTER (WHERE c.scrape_date = max_d - INTERVAL '5 days') AS "D-5",
                    COUNT(*) FILTER (WHERE c.scrape_date = max_d - INTERVAL '6 days') AS "D-6",
                    COUNT(*) AS "Total 14D Records"
                FROM silver.clean_store_prices c
                CROSS JOIN date_bounds
                LEFT JOIN gold.dim_stores st ON st.store_slug = c.store_slug
                WHERE c.scrape_date >= max_d - INTERVAL '14 days'
                [[ AND c.store_slug = {{store_slug}} ]]
                GROUP BY st.store_name, c.store_slug
                ORDER BY "Latest" DESC;
            """,
            "viz": {"table.pivot_column": None},
            "template_tags": {
                "store_slug": {
                    "id": "tt_ops_store_matrix",
                    "name": "store_slug",
                    "display-name": "Store Selector",
                    "type": "text"
                }
            },
            "mappings": [
                {
                    "parameter_id": "param_store",
                    "target": ["variable", ["template-tag", "store_slug"]]
                }
            ],
            "grid": (0, 27, 12, 8)
        },
        {
            "name": "Scraper Field Extraction Completeness (%)",
            "desc": "Completeness audit of barcode, brand, category, size unit, and promo rates per store.",
            "display": "table",
            "sql": """
                SELECT 
                    COALESCE(st.store_name, c.store_slug) AS "Store Name",
                    c.store_slug AS "Store Slug",
                    COUNT(*) AS "Total Items",
                    ROUND((COUNT(c.barcode) FILTER (WHERE c.barcode IS NOT NULL AND TRIM(c.barcode) <> '') * 100.0 / COUNT(*))::numeric, 1) AS "Barcode (%)",
                    ROUND((COUNT(c.brand) FILTER (WHERE c.brand IS NOT NULL AND TRIM(c.brand) <> '') * 100.0 / COUNT(*))::numeric, 1) AS "Brand (%)",
                    ROUND((COUNT(c.category_native) FILTER (WHERE c.category_native IS NOT NULL AND TRIM(c.category_native) <> '') * 100.0 / COUNT(*))::numeric, 1) AS "Category Native (%)",
                    ROUND((COUNT(c.size_unit) FILTER (WHERE c.size_unit IS NOT NULL AND TRIM(c.size_unit) <> '') * 100.0 / COUNT(*))::numeric, 1) AS "Unit Size (%)",
                    ROUND((COUNT(*) FILTER (WHERE c.discount_pct IS NOT NULL AND c.discount_pct > 0) * 100.0 / COUNT(*))::numeric, 1) AS "Promo Rate (%)"
                FROM silver.clean_store_prices c
                LEFT JOIN gold.dim_stores st ON st.store_slug = c.store_slug
                WHERE c.scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices)
                [[ AND c.store_slug = {{store_slug}} ]]
                GROUP BY st.store_name, c.store_slug
                ORDER BY "Total Items" DESC;
            """,
            "viz": {"table.pivot_column": None},
            "template_tags": {
                "store_slug": {
                    "id": "tt_ops_store_extract",
                    "name": "store_slug",
                    "display-name": "Store Selector",
                    "type": "text"
                }
            },
            "mappings": [
                {
                    "parameter_id": "param_store",
                    "target": ["variable", ["template-tag", "store_slug"]]
                }
            ],
            "grid": (12, 27, 12, 8)
        }
    ]

    for item in ops_cards:
        cid = create_or_update_card(
            cur, item["name"], item["desc"], item["display"], item["sql"], item["viz"], c_ops,
            db_id=db_id, template_tags=item.get("template_tags")
        )
        col, row, sx, sy = item["grid"]
        mappings = []
        for m in item.get("mappings") or []:
            cm = dict(m)
            cm["card_id"] = cid
            mappings.append(cm)
        place_card_on_dashboard(cur, d_ops_id, cid, col, row, sx, sy, item["viz"], parameter_mappings=mappings)

    # ═══════════════════════════════════════════════════════════════════════════
    # 3. 🛡️ DASHBOARD 3: SILVER DATA QUALITY SCREENER
    # ═══════════════════════════════════════════════════════════════════════════
    col_name_3 = "03 - Silver Data Quality Screener"
    dash_name_3 = "03 - Silver Data Quality Screener"

    print("[3/3] Setting up Collection 03: Silver Data Quality Screener...")
    c_class = get_or_create_collection(
        cur,
        col_name_3,
        "Pre-CPI quality gate, COICOP classification completeness, log-price distributions, outlier screening, and human review queues.",
        "#9B59B6"
    )

    dash_3_params = [
        {
            "id": "param_div",
            "name": "COICOP Division",
            "slug": "coicop_division",
            "type": "category",
            "sectionId": "string"
        },
        {
            "id": "param_store",
            "name": "Store Selector",
            "slug": "store_slug",
            "type": "category",
            "sectionId": "string"
        }
    ]

    d_class_id = create_or_update_dashboard(
        cur,
        dash_name_3,
        "Silver layer quality control: Pre-CPI Quality Gate, COICOP coverage & method breakdown, price outliers, imputation rates, and review queue.",
        c_class,
        parameters=dash_3_params
    )

    class_cards = [
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
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices)
                [[ AND store_slug = {{store_slug}} ]];
            """,
            "viz": {},
            "template_tags": {
                "store_slug": {
                    "id": "tt_class_qg_store",
                    "name": "store_slug",
                    "display-name": "Store Selector",
                    "type": "text"
                }
            },
            "mappings": [
                {
                    "parameter_id": "param_store",
                    "target": ["variable", ["template-tag", "store_slug"]]
                }
            ],
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
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices)
                [[ AND store_slug = {{store_slug}} ]];
            """,
            "viz": {},
            "template_tags": {
                "store_slug": {
                    "id": "tt_class_cov_store",
                    "name": "store_slug",
                    "display-name": "Store Selector",
                    "type": "text"
                }
            },
            "mappings": [
                {
                    "parameter_id": "param_store",
                    "target": ["variable", ["template-tag", "store_slug"]]
                }
            ],
            "grid": (6, 0, 6, 3)
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
                [[ AND coicop_division = {{coicop_division}} ]]
                [[ AND store_slug = {{store_slug}} ]]
                GROUP BY coicop_division
                ORDER BY "Product Count" DESC;
            """,
            "viz": {
                "graph.dimensions": ["COICOP Division"],
                "graph.metrics": ["Product Count"]
            },
            "template_tags": {
                "coicop_division": {
                    "id": "tt_class_dist_div",
                    "name": "coicop_division",
                    "display-name": "COICOP Division",
                    "type": "text"
                },
                "store_slug": {
                    "id": "tt_class_dist_store",
                    "name": "store_slug",
                    "display-name": "Store Selector",
                    "type": "text"
                }
            },
            "mappings": [
                {
                    "parameter_id": "param_div",
                    "target": ["variable", ["template-tag", "coicop_division"]]
                },
                {
                    "parameter_id": "param_store",
                    "target": ["variable", ["template-tag", "store_slug"]]
                }
            ],
            "grid": (0, 3, 12, 8)
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
                [[ AND store_slug = {{store_slug}} ]]
                GROUP BY coicop_method
                ORDER BY "Item Count" DESC;
            """,
            "viz": {
                "graph.dimensions": ["Classification Method"],
                "graph.metrics": ["Item Count"]
            },
            "template_tags": {
                "store_slug": {
                    "id": "tt_class_method_store",
                    "name": "store_slug",
                    "display-name": "Store Selector",
                    "type": "text"
                }
            },
            "mappings": [
                {
                    "parameter_id": "param_store",
                    "target": ["variable", ["template-tag", "store_slug"]]
                }
            ],
            "grid": (12, 3, 12, 8)
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
            "grid": (0, 11, 12, 8)
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
                [[ AND coicop_division = {{coicop_division}} ]]
                GROUP BY coicop_division
                ORDER BY coicop_division ASC;
            """,
            "viz": {
                "graph.dimensions": ["Division Code"],
                "graph.metrics": ["Imputation Rate (%)"]
            },
            "template_tags": {
                "coicop_division": {
                    "id": "tt_class_imp_div",
                    "name": "coicop_division",
                    "display-name": "COICOP Division",
                    "type": "text"
                }
            },
            "mappings": [
                {
                    "parameter_id": "param_div",
                    "target": ["variable", ["template-tag", "coicop_division"]]
                }
            ],
            "grid": (12, 11, 12, 8)
        },
        {
            "name": "Silver Flagged Price Outliers & Fallback Audits",
            "desc": "High-risk records flagged for price abnormalities or scraper selector fallbacks in Silver.",
            "display": "table",
            "sql": """
                SELECT 
                    c.scrape_date AS "Date",
                    COALESCE(st.store_name, c.store_slug) AS "Store Name",
                    c.store_slug AS "Store Slug",
                    c.name_clean AS "Product Name",
                    c.price_khr AS "Price (KHR)",
                    c.unit_price_khr AS "Unit Price (KHR)",
                    c.coicop_division AS "Div",
                    c.is_outlier AS "Outlier",
                    c.fallback_reason AS "Audit Reason"
                FROM silver.clean_store_prices c
                LEFT JOIN gold.dim_stores st ON st.store_slug = c.store_slug
                WHERE c.scrape_date = (SELECT MAX(scrape_date) FROM silver.clean_store_prices)
                  AND (c.is_outlier = TRUE OR c.is_fallback = TRUE)
                [[ AND c.coicop_division = {{coicop_division}} ]]
                [[ AND c.store_slug = {{store_slug}} ]]
                ORDER BY c.is_outlier DESC, c.price_khr DESC
                LIMIT 30;
            """,
            "viz": {"table.pivot_column": None},
            "template_tags": {
                "coicop_division": {
                    "id": "tt_class_outliers_div",
                    "name": "coicop_division",
                    "display-name": "COICOP Division",
                    "type": "text"
                },
                "store_slug": {
                    "id": "tt_class_outliers_store",
                    "name": "store_slug",
                    "display-name": "Store Selector",
                    "type": "text"
                }
            },
            "mappings": [
                {
                    "parameter_id": "param_div",
                    "target": ["variable", ["template-tag", "coicop_division"]]
                },
                {
                    "parameter_id": "param_store",
                    "target": ["variable", ["template-tag", "store_slug"]]
                }
            ],
            "grid": (0, 19, 14, 8)
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
            "grid": (14, 19, 10, 8)
        }
    ]

    for item in class_cards:
        cid = create_or_update_card(
            cur, item["name"], item["desc"], item["display"], item["sql"], item["viz"], c_class,
            db_id=db_id, template_tags=item.get("template_tags")
        )
        col, row, sx, sy = item["grid"]
        mappings = []
        for m in item.get("mappings") or []:
            cm = dict(m)
            cm["card_id"] = cid
            mappings.append(cm)
        place_card_on_dashboard(cur, d_class_id, cid, col, row, sx, sy, item["viz"], parameter_mappings=mappings)

    cur.execute("DELETE FROM query_cache;")
    conn.commit()
    conn.close()

    print("\n=============================================================================")
    print("SUCCESS: 3 Canonical Metabase Dashboards fully provisioned!")
    print(f"  [1] Macro CPI & Inflation Analytics ID: {d_cpi_id} | Collection: {col_name_1}")
    print(f"  [2] Operations & 25-Source Telemetry ID: {d_ops_id} | Collection: {col_name_2}")
    print(f"  [3] Silver Data Quality Screener ID: {d_class_id} | Collection: {col_name_3}")
    print("  Metabase URL: http://localhost:3001 (or :3000)")
    print("=============================================================================")

if __name__ == "__main__":
    provision_all()
