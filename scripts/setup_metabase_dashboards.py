"""
=============================================================================
CAMBODIA CPI PIPELINE — METABASE DASHBOARD AUTOMATED PROVISIONER
Provisions 4 Executive & Engineering Dashboards + 38 Analytical Questions
directly into Metabase application database (PostgreSQL port 5432).
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

def get_or_create_collection(cur, name, description, color="#509EE3", parent_id=None):
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

def provision_all():
    conn = psycopg2.connect("postgresql://metabase:metabase@localhost:5432/metabase")
    cur = conn.cursor()
    
    print("[1/5] Setting up Collections in Metabase...")
    c_macro = get_or_create_collection(cur, "01 - Cambodia Executive Inflation Observatory", "National CPI Headline, Multilateral GEKS, Fisher Indices & Inflation Momentum", "#2E5BFF")
    c_div = get_or_create_collection(cur, "02 - UN COICOP Division & Price Dynamics", "12 Division trends, staple commodity shifts & granular product explorer", "#00C9A7")
    c_promo = get_or_create_collection(cur, "03 - Retailer Competition & Promo Analytics", "Cross-store price dispersion, retailer price leadership & promotional savings", "#FF808B")
    c_ops = get_or_create_collection(cur, "04 - Scraper Operations & Data Ops", "20-source scraper availability matrix, daily volumes & price anomaly alerts", "#845EC2")

    # =========================================================================
    # DASHBOARD 1: Cambodia National Inflation & Macroeconomic CPI Observatory
    # =========================================================================
    print("[2/5] Building Dashboard 1: Executive Inflation Observatory...")
    d1_id = create_or_update_dashboard(cur, "Cambodia National Inflation & Macroeconomic CPI Observatory", 
        "Executive inflation overview across 12 UN COICOP Divisions with Laspeyres, Multilateral GEKS-Tornqvist, Fisher Superlative and Official MEF Exchange Rates.", c_macro)
    
    d1_cards = [
        {
            "name": "Headline CPI (Laspeyres Base=100)",
            "desc": "Official daily national headline Laspeyres Consumer Price Index relative to August 2026 reference period.",
            "display": "scalar",
            "sql": "SELECT cpi_headline_khr AS \"Headline CPI (KHR)\" FROM gold.mart_cpi_daily ORDER BY scrape_date DESC LIMIT 1;",
            "viz": {},
            "grid": (0, 0, 4, 3)
        },
        {
            "name": "Day-on-Day Inflation Rate (%)",
            "desc": "24-hour percentage change in national headline CPI.",
            "display": "scalar",
            "sql": "SELECT inflation_dod_pct AS \"DoD Inflation (%)\" FROM gold.mart_cpi_daily ORDER BY scrape_date DESC LIMIT 1;",
            "viz": {},
            "grid": (4, 0, 4, 3)
        },
        {
            "name": "Month-on-Month Inflation Rate (%)",
            "desc": "30-day rolling percentage change in national headline CPI.",
            "display": "scalar",
            "sql": "SELECT inflation_mom_pct AS \"MoM Inflation (%)\" FROM gold.mart_cpi_daily ORDER BY scrape_date DESC LIMIT 1;",
            "viz": {},
            "grid": (8, 0, 4, 3)
        },
        {
            "name": "Multilateral GEKS-Törnqvist Index",
            "desc": "13-period rolling window transitive multilateral price index eliminating base-period chain drift.",
            "display": "scalar",
            "sql": "SELECT cpi_geks_multilateral AS \"GEKS Multilateral CPI\" FROM gold.mart_cpi_daily ORDER BY scrape_date DESC LIMIT 1;",
            "viz": {},
            "grid": (12, 0, 4, 3)
        },
        {
            "name": "Consumer Substitution Bias (%)",
            "desc": "Upper-level substitution bias measured as the spread between fixed-basket Laspeyres and Fisher Superlative index.",
            "display": "scalar",
            "sql": "SELECT substitution_bias_pct AS \"Substitution Bias (%)\" FROM gold.cpi_fisher_superlative ORDER BY scrape_date DESC LIMIT 1;",
            "viz": {},
            "grid": (16, 0, 4, 3)
        },
        {
            "name": "MEF USD / KHR Official Rate",
            "desc": "Official daily exchange rate from Ministry of Economy and Finance (MEF API).",
            "display": "scalar",
            "sql": "SELECT usd_khr_exchange_rate AS \"USD/KHR Rate\" FROM gold.v_monitor_fx_health ORDER BY execution_date DESC LIMIT 1;",
            "viz": {},
            "grid": (20, 0, 4, 3)
        },
        {
            "name": "National Headline CPI Trajectory (Time-Series Comparison)",
            "desc": "Comparison of Laspeyres Headline CPI, Multilateral GEKS-Törnqvist, Core CPI (Excl Food & Fuel), and USD-Denominated CPI.",
            "display": "line",
            "sql": """
                SELECT 
                    scrape_date,
                    cpi_headline_khr AS "Laspeyres Headline",
                    cpi_geks_multilateral AS "GEKS-Tornqvist Multilateral",
                    cpi_core_khr AS "Core CPI (Excl Food & Energy)",
                    cpi_headline_usd AS "USD Denominated CPI"
                FROM gold.mart_cpi_daily
                ORDER BY scrape_date ASC;
            """,
            "viz": {
                "graph.dimensions": ["scrape_date"],
                "graph.metrics": ["Laspeyres Headline", "GEKS-Tornqvist Multilateral", "Core CPI (Excl Food & Energy)", "USD Denominated CPI"],
                "graph.x_axis.scale": "timeseries",
                "graph.colors": ["#2E5BFF", "#00C9A7", "#FF9F43", "#845EC2"]
            },
            "grid": (0, 3, 14, 8)
        },
        {
            "name": "Inflation Momentum (DoD vs MoM %)",
            "desc": "Day-on-Day and Month-on-Month inflation momentum dynamics.",
            "display": "line",
            "sql": """
                SELECT 
                    scrape_date,
                    inflation_dod_pct AS "Day-on-Day (%)",
                    inflation_mom_pct AS "Month-on-Month (%)"
                FROM gold.mart_cpi_daily
                ORDER BY scrape_date ASC;
            """,
            "viz": {
                "graph.dimensions": ["scrape_date"],
                "graph.metrics": ["Day-on-Day (%)", "Month-on-Month (%)"],
                "graph.x_axis.scale": "timeseries",
                "graph.colors": ["#FF808B", "#2E5BFF"]
            },
            "grid": (14, 3, 10, 8)
        },
        {
            "name": "12 UN COICOP Division Weights & Current Indices",
            "desc": "Official Cambodia NIS basket weights compared against latest division-level price indices.",
            "display": "table",
            "sql": """
                SELECT 
                    coicop_division AS "Division Code",
                    division_name AS "COICOP Division",
                    weight_pct AS "NIS Weight (%)",
                    division_index_khr AS "Current Price Index",
                    dod_change_pct AS "DoD Change (%)",
                    mom_change_pct AS "MoM Change (%)",
                    active_items_count AS "Tracked Items",
                    promo_share_pct AS "Promo Share (%)"
                FROM gold.mart_cpi_division_daily
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM gold.mart_cpi_division_daily)
                ORDER BY coicop_division ASC;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 11, 14, 8)
        },
        {
            "name": "Superlative Fisher Ideal vs Laspeyres Index",
            "desc": "Evaluating consumer substitution elasticity with Fisher Superlative Index and Paasche Index.",
            "display": "line",
            "sql": """
                SELECT 
                    scrape_date,
                    laspeyres_index AS "Laspeyres Index",
                    paasche_index AS "Paasche Index",
                    fisher_index AS "Fisher Superlative",
                    substitution_bias_pct AS "Substitution Bias (%)"
                FROM gold.cpi_fisher_superlative
                ORDER BY scrape_date ASC;
            """,
            "viz": {
                "graph.dimensions": ["scrape_date"],
                "graph.metrics": ["Laspeyres Index", "Paasche Index", "Fisher Superlative"],
                "graph.x_axis.scale": "timeseries"
            },
            "grid": (14, 11, 10, 8)
        },
        {
            "name": "National Daily CPI Audit History",
            "desc": "Complete historical log of daily national price indices, statistical coverage, and imputation audit.",
            "display": "table",
            "sql": """
                SELECT 
                    scrape_date AS "Date",
                    cpi_headline_khr AS "Headline CPI (KHR)",
                    cpi_geks_multilateral AS "GEKS CPI",
                    cpi_core_khr AS "Core CPI",
                    inflation_dod_pct AS "DoD Inflation (%)",
                    inflation_mom_pct AS "MoM Inflation (%)",
                    divisions_present AS "Divisions Present",
                    total_weight_covered AS "Weight Covered (%)",
                    active_quotes_count AS "Active Quotes",
                    imputed_quote_pct AS "Imputed Quotes (%)"
                FROM gold.mart_cpi_daily
                ORDER BY scrape_date DESC;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 19, 24, 7)
        }
    ]
    
    for item in d1_cards:
        cid = create_or_update_card(cur, item["name"], item["desc"], item["display"], item["sql"], item["viz"], c_macro)
        col, row, sx, sy = item["grid"]
        place_card_on_dashboard(cur, d1_id, cid, col, row, sx, sy, item["viz"])

    # =========================================================================
    # DASHBOARD 2: UN COICOP Division & Basket Dynamics
    # =========================================================================
    print("[3/5] Building Dashboard 2: COICOP Division Deep Dive...")
    d2_id = create_or_update_dashboard(cur, "UN COICOP Division & Price Dynamics Deep-Dive", 
        "Granular price index trajectory across all 12 UN COICOP divisions, top inflation commodity movers, and product explorer.", c_div)

    d2_cards = [
        {
            "name": "Food & Non-Alcoholic Beverages (Div 01 - 44.8% Weight)",
            "desc": "Latest index for Food and Non-Alcoholic Beverages division.",
            "display": "scalar",
            "sql": "SELECT division_index_khr FROM gold.mart_cpi_division_daily WHERE coicop_division = '01' ORDER BY scrape_date DESC LIMIT 1;",
            "viz": {},
            "grid": (0, 0, 6, 3)
        },
        {
            "name": "Housing, Water & Energy (Div 04 - 17.1% Weight)",
            "desc": "Latest index for Housing, Utilities and Fuels division.",
            "display": "scalar",
            "sql": "SELECT division_index_khr FROM gold.mart_cpi_division_daily WHERE coicop_division = '04' ORDER BY scrape_date DESC LIMIT 1;",
            "viz": {},
            "grid": (6, 0, 6, 3)
        },
        {
            "name": "Transport & Fuel (Div 07 - 12.2% Weight)",
            "desc": "Latest index for Transport division.",
            "display": "scalar",
            "sql": "SELECT division_index_khr FROM gold.mart_cpi_division_daily WHERE coicop_division = '07' ORDER BY scrape_date DESC LIMIT 1;",
            "viz": {},
            "grid": (12, 0, 6, 3)
        },
        {
            "name": "Health & Medical (Div 06 - 5.6% Weight)",
            "desc": "Latest index for Health and Pharmaceuticals division.",
            "display": "scalar",
            "sql": "SELECT division_index_khr FROM gold.mart_cpi_division_daily WHERE coicop_division = '06' ORDER BY scrape_date DESC LIMIT 1;",
            "viz": {},
            "grid": (18, 0, 6, 3)
        },
        {
            "name": "All 12 COICOP Divisions Daily Inflation Trajectory",
            "desc": "Time-series price index trajectory comparing all 12 COICOP divisions over time.",
            "display": "line",
            "sql": """
                SELECT 
                    scrape_date,
                    coicop_division || ' - ' || division_name AS division_label,
                    division_index_khr AS index_value
                FROM gold.mart_cpi_division_daily
                ORDER BY scrape_date ASC, coicop_division ASC;
            """,
            "viz": {
                "graph.dimensions": ["scrape_date", "division_label"],
                "graph.metrics": ["index_value"],
                "graph.x_axis.scale": "timeseries"
            },
            "grid": (0, 3, 14, 8)
        },
        {
            "name": "Division Inflation Contribution to Headline CPI",
            "desc": "Net inflation contribution points computed as Weight (%) * (Division Index - 100).",
            "display": "bar",
            "sql": """
                SELECT 
                    division_name AS "Division",
                    ROUND(weight_pct * (division_index_khr - 100.0) / 100.0, 3) AS "Inflation Contribution (pts)"
                FROM gold.mart_cpi_division_daily
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM gold.mart_cpi_division_daily)
                ORDER BY "Inflation Contribution (pts)" DESC;
            """,
            "viz": {
                "graph.dimensions": ["Division"],
                "graph.metrics": ["Inflation Contribution (pts)"],
                "graph.colors": ["#2E5BFF"]
            },
            "grid": (14, 3, 10, 8)
        },
        {
            "name": "Top 15 High-Inflation Commodity Spikes (DoD Surge)",
            "desc": "Items experiencing significant day-on-day price increases.",
            "display": "table",
            "sql": """
                SELECT 
                    name_clean AS "Commodity / Item",
                    store_slug AS "Retailer",
                    coicop_division AS "Division",
                    yesterday_price_khr AS "Yesterday Price (KHR)",
                    today_price_khr AS "Today Price (KHR)",
                    dod_price_change_pct AS "Price Shift (%)",
                    alert_level AS "Severity"
                FROM gold.v_monitor_price_alerts
                WHERE dod_price_change_pct > 0
                  AND scrape_date = (SELECT MAX(scrape_date) FROM gold.v_monitor_price_alerts)
                ORDER BY dod_price_change_pct DESC
                LIMIT 15;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 11, 12, 8)
        },
        {
            "name": "Top 15 Deflationary Items / Price Drops",
            "desc": "Items experiencing steep price drops or post-promotional discounts.",
            "display": "table",
            "sql": """
                SELECT 
                    name_clean AS "Commodity / Item",
                    store_slug AS "Retailer",
                    coicop_division AS "Division",
                    yesterday_price_khr AS "Yesterday Price (KHR)",
                    today_price_khr AS "Today Price (KHR)",
                    dod_price_change_pct AS "Price Drop (%)",
                    alert_level AS "Severity"
                FROM gold.v_monitor_price_alerts
                WHERE dod_price_change_pct < 0
                  AND scrape_date = (SELECT MAX(scrape_date) FROM gold.v_monitor_price_alerts)
                ORDER BY dod_price_change_pct ASC
                LIMIT 15;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (12, 11, 12, 8)
        },
        {
            "name": "Tracked Item Quotes & Stores per Division",
            "desc": "Number of active price quotes and retail stores participating in each COICOP division.",
            "display": "bar",
            "sql": """
                SELECT 
                    coicop_division || ' - ' || division_name AS "Division",
                    active_items_count AS "Active Items Tracked",
                    stores_count AS "Retailers Quoting"
                FROM gold.mart_cpi_division_daily
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM gold.mart_cpi_division_daily)
                ORDER BY active_items_count DESC;
            """,
            "viz": {
                "graph.dimensions": ["Division"],
                "graph.metrics": ["Active Items Tracked", "Retailers Quoting"]
            },
            "grid": (0, 19, 24, 7)
        },
        {
            "name": "Granular Product-Level Price Explorer",
            "desc": "Searchable item-level table displaying Jevons geometric mean price, reference base price, and store count.",
            "display": "table",
            "sql": """
                SELECT 
                    j.scrape_date AS "Date",
                    j.coicop_division AS "Div",
                    COALESCE(m.canonical_name, j.item_id) AS "Canonical Product Name",
                    j.p_khr_jevons AS "Current Jevons Price (KHR)",
                    b.base_price_khr AS "Base Price (KHR)",
                    ROUND((j.p_khr_jevons / NULLIF(b.base_price_khr, 0)) * 100.0, 2) AS "Jevons Index (Base=100)",
                    j.n_quotes AS "Quotes Count",
                    j.n_stores AS "Store Count"
                FROM gold.fct_daily_price_stats j
                LEFT JOIN silver.dim_items m ON m.item_id = j.item_id
                LEFT JOIN gold.base_prices b ON b.product_key = j.item_id
                WHERE j.scrape_date = (SELECT MAX(scrape_date) FROM gold.fct_daily_price_stats)
                ORDER BY j.coicop_division ASC, j.p_khr_jevons DESC
                LIMIT 100;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 26, 24, 8)
        }
    ]

    for item in d2_cards:
        cid = create_or_update_card(cur, item["name"], item["desc"], item["display"], item["sql"], item["viz"], c_div)
        col, row, sx, sy = item["grid"]
        place_card_on_dashboard(cur, d2_id, cid, col, row, sx, sy, item["viz"])

    # =========================================================================
    # DASHBOARD 3: Retailer Competition & Promo Analytics
    # =========================================================================
    print("[4/5] Building Dashboard 3: Retailer Competition & Promo Analytics...")
    d3_id = create_or_update_dashboard(cur, "Retailer Competition, Cross-Store Dispersion & Promotion Analytics", 
        "Price dispersion for identical goods across retail chains, retailer price leadership, promotional penetration, and discount depth.", c_promo)

    d3_cards = [
        {
            "name": "Average Catalog Promotion Penetration (%)",
            "desc": "Percentage of all scraped listings carrying an active promotional discount tag.",
            "display": "scalar",
            "sql": "SELECT ROUND(AVG(promo_penetration_pct), 2) AS \"Promo Penetration (%)\" FROM silver.v_promo_analytics WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.v_promo_analytics);",
            "viz": {},
            "grid": (0, 0, 6, 3)
        },
        {
            "name": "Average Promotional Discount Depth (%)",
            "desc": "Average discount percentage applied to on-sale items.",
            "display": "scalar",
            "sql": "SELECT ROUND(AVG(avg_discount_pct), 2) AS \"Avg Discount Depth (%)\" FROM silver.v_promo_analytics WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.v_promo_analytics) AND avg_discount_pct IS NOT NULL;",
            "viz": {},
            "grid": (6, 0, 6, 3)
        },
        {
            "name": "Promotional Deflation Savings (%)",
            "desc": "Effective savings passed on to consumers relative to standard regular shelf prices.",
            "display": "scalar",
            "sql": "SELECT ROUND(AVG(promo_deflation_savings_pct), 2) AS \"Consumer Savings (%)\" FROM silver.v_promo_analytics WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.v_promo_analytics);",
            "viz": {},
            "grid": (12, 0, 6, 3)
        },
        {
            "name": "Cross-Store Matched Identical Products",
            "desc": "Count of distinct canonical products actively quoted across multiple competing supermarkets/stores.",
            "display": "scalar",
            "sql": "SELECT COUNT(DISTINCT item_id) AS \"Multi-Store Items\" FROM silver.v_cross_store_dispersion WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.v_cross_store_dispersion);",
            "viz": {},
            "grid": (18, 0, 6, 3)
        },
        {
            "name": "Identical Item Cross-Store Price Dispersion",
            "desc": "Comparing lowest vs highest price for identical canonical products across AEON, Delishop, Bayon, etc.",
            "display": "table",
            "sql": """
                SELECT 
                    canonical_name AS "Product Name",
                    brand AS "Brand",
                    coicop_division AS "Division",
                    retailer_count AS "Stores Quoting",
                    min_price_khr AS "Min Price (KHR)",
                    max_price_khr AS "Max Price (KHR)",
                    price_spread_pct AS "Price Spread (%)",
                    cheapest_store AS "Lowest Price Retailer",
                    most_expensive_store AS "Highest Price Retailer"
                FROM silver.v_cross_store_dispersion
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.v_cross_store_dispersion)
                ORDER BY price_spread_pct DESC
                LIMIT 30;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 3, 14, 9)
        },
        {
            "name": "Retailer Price Competitiveness Leaderboard",
            "desc": "Share of matched items where each store provides the lowest market price.",
            "display": "bar",
            "sql": """
                SELECT 
                    cheapest_store AS "Retailer",
                    COUNT(*) AS "Lowest Price Quotes",
                    ROUND(COUNT(*)::NUMERIC / SUM(COUNT(*)) OVER () * 100.0, 1) AS "Market Price Leadership (%)"
                FROM silver.v_cross_store_dispersion
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.v_cross_store_dispersion)
                GROUP BY cheapest_store
                ORDER BY "Lowest Price Quotes" DESC;
            """,
            "viz": {
                "graph.dimensions": ["Retailer"],
                "graph.metrics": ["Lowest Price Quotes"],
                "graph.colors": ["#00C9A7"]
            },
            "grid": (14, 3, 10, 9)
        },
        {
            "name": "Promotional Activity by Retailer",
            "desc": "Total promotional items, promo catalog penetration, and average discount depth per store.",
            "display": "table",
            "sql": """
                SELECT 
                    store_slug AS "Retailer",
                    SUM(total_scraped_items) AS "Total Catalog Items",
                    SUM(promo_items_count) AS "Promo Items Count",
                    ROUND(AVG(promo_penetration_pct), 1) AS "Promo Penetration (%)",
                    ROUND(AVG(avg_discount_pct), 1) AS "Avg Discount Depth (%)",
                    ROUND(AVG(promo_deflation_savings_pct), 1) AS "Consumer Savings (%)"
                FROM silver.v_promo_analytics
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.v_promo_analytics)
                GROUP BY store_slug
                ORDER BY "Promo Items Count" DESC;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 12, 12, 8)
        },
        {
            "name": "Promotional Share by COICOP Division",
            "desc": "Promotional discount intensity across product categories.",
            "display": "bar",
            "sql": """
                SELECT 
                    coicop_division AS "COICOP Division",
                    SUM(promo_items_count) AS "Promotional Items",
                    ROUND(AVG(promo_penetration_pct), 1) AS "Promo Penetration (%)"
                FROM silver.v_promo_analytics
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.v_promo_analytics)
                GROUP BY coicop_division
                ORDER BY "Promotional Items" DESC;
            """,
            "viz": {
                "graph.dimensions": ["COICOP Division"],
                "graph.metrics": ["Promotional Items"],
                "graph.colors": ["#FF808B"]
            },
            "grid": (12, 12, 12, 8)
        }
    ]

    for item in d3_cards:
        cid = create_or_update_card(cur, item["name"], item["desc"], item["display"], item["sql"], item["viz"], c_promo)
        col, row, sx, sy = item["grid"]
        place_card_on_dashboard(cur, d3_id, cid, col, row, sx, sy, item["viz"])

    # =========================================================================
    # DASHBOARD 4: Scraper Operations & Data Ops
    # =========================================================================
    print("[5/5] Building Dashboard 4: Scraper Operations & Data Ops...")
    d4_id = create_or_update_dashboard(cur, "Scraper Operations, Data Pipeline Health & Anomaly Triage", 
        "Real-time operational observability for all 20 scrapers, daily ingestion volume trends, and automated price anomaly detection alerts.", c_ops)

    d4_cards = [
        {
            "name": "Online Scrapers Count (20-Source Registry)",
            "desc": "Number of production scrapers with fresh data ingested within the last 24 hours.",
            "display": "scalar",
            "sql": "SELECT COUNT(*) AS \"Online Scrapers\" FROM gold.v_monitor_source_health_matrix WHERE pipeline_health IN ('ONLINE_FRESH', 'ONLINE_YESTERDAY');",
            "viz": {},
            "grid": (0, 0, 6, 3)
        },
        {
            "name": "Today Total Ingested Items",
            "desc": "Sum of all atomic product price observations scraped and validated today.",
            "display": "scalar",
            "sql": "SELECT SUM(total_items_scraped) AS \"Total Items Today\" FROM gold.v_monitor_scraper_daily WHERE scrape_date = (SELECT MAX(scrape_date) FROM gold.v_monitor_scraper_daily);",
            "viz": {},
            "grid": (6, 0, 6, 3)
        },
        {
            "name": "MEF Official USD/KHR Rate",
            "desc": "Official exchange rate used for foreign currency conversion into KHR.",
            "display": "scalar",
            "sql": "SELECT usd_khr_exchange_rate FROM gold.v_monitor_fx_health ORDER BY execution_date DESC LIMIT 1;",
            "viz": {},
            "grid": (12, 0, 6, 3)
        },
        {
            "name": "Flagged Price Anomaly Alerts (>20% Shift)",
            "desc": "Active anomaly alerts exceeding the ±20% single-day price variation threshold.",
            "display": "scalar",
            "sql": "SELECT COUNT(*) AS \"Anomaly Alerts\" FROM gold.v_monitor_price_alerts WHERE scrape_date = (SELECT MAX(scrape_date) FROM gold.v_monitor_price_alerts);",
            "viz": {},
            "grid": (18, 0, 6, 3)
        },
        {
            "name": "20-Source Scraper Availability Matrix",
            "desc": "Real-time health matrix showing latest ingestion date, lag in days, 7-day average volume, and operational status.",
            "display": "table",
            "sql": """
                SELECT 
                    store_slug AS "Source / Store Slug",
                    latest_scrape_date AS "Latest Ingestion Date",
                    days_since_last_scrape AS "Lag (Days)",
                    avg_daily_volume_7d AS "7D Avg Volume",
                    active_days_last_7d AS "Active Days (7D)",
                    pipeline_health AS "Operational Status"
                FROM gold.v_monitor_source_health_matrix
                ORDER BY days_since_last_scrape ASC, avg_daily_volume_7d DESC;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 3, 14, 8)
        },
        {
            "name": "Daily Ingested Volume by Store (Last 14 Days)",
            "desc": "Volume trajectory per retailer illustrating scraper consistency and historical ingestion runs.",
            "display": "bar",
            "sql": """
                SELECT 
                    scrape_date,
                    store_slug,
                    total_items_scraped
                FROM gold.v_monitor_scraper_daily
                WHERE scrape_date >= CURRENT_DATE - INTERVAL '14 days'
                ORDER BY scrape_date ASC, store_slug ASC;
            """,
            "viz": {
                "graph.dimensions": ["scrape_date", "store_slug"],
                "graph.metrics": ["total_items_scraped"],
                "graph.x_axis.scale": "timeseries",
                "stackable.stack_type": "stacked"
            },
            "grid": (14, 3, 10, 8)
        },
        {
            "name": "Real-Time Price Anomaly & Extreme Shift Feed",
            "desc": "Live feed of extreme price movements requiring validation (e.g. unit changes, out-of-stock typos, flash sales).",
            "display": "table",
            "sql": """
                SELECT 
                    scrape_date AS "Date",
                    store_slug AS "Retailer",
                    name_clean AS "Product Name",
                    coicop_division AS "Division",
                    yesterday_price_khr AS "Yesterday Price (KHR)",
                    today_price_khr AS "Today Price (KHR)",
                    dod_price_change_pct AS "Shift (%)",
                    alert_level AS "Severity"
                FROM gold.v_monitor_price_alerts
                ORDER BY scrape_date DESC, ABS(dod_price_change_pct) DESC
                LIMIT 50;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (0, 11, 14, 8)
        },
        {
            "name": "Pipeline Quality & Coverage Guardrails",
            "desc": "Daily data quality metrics: deduplication rate, barcode coverage, outlier filtering, and LOCF imputation rates.",
            "display": "table",
            "sql": """
                SELECT 
                    scrape_date AS "Date",
                    store_slug AS "Store",
                    total_observations AS "Raw Observations",
                    unique_products AS "Unique Items",
                    classification_rate_pct AS "Classification (%)",
                    barcode_coverage_pct AS "Barcode Coverage (%)",
                    outlier_count AS "Outliers",
                    imputed_count AS "LOCF Imputed",
                    imputation_rate_pct AS "Imputation (%)"
                FROM gold.v_coverage
                WHERE scrape_date >= CURRENT_DATE - INTERVAL '7 days'
                ORDER BY scrape_date DESC, total_observations DESC;
            """,
            "viz": {"table.pivot_column": None},
            "grid": (14, 11, 10, 8)
        },
        {
            "name": "Hybrid COICOP Classification Pipeline Throughput",
            "desc": "Breakdown of classification methods utilized across the 9-tier hybrid ladder (Overrides, Purity, AI Cache, Traps, Keywords, Category Map).",
            "display": "bar",
            "sql": """
                SELECT 
                    coicop_method AS "Classification Ladder Tier",
                    COUNT(*) AS "Items Classified",
                    ROUND(COUNT(*)::NUMERIC / SUM(COUNT(*)) OVER () * 100.0, 1) AS "Share (%)"
                FROM silver.fct_daily_prices
                WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.fct_daily_prices)
                  AND coicop_method IS NOT NULL
                GROUP BY coicop_method
                ORDER BY "Items Classified" DESC;
            """,
            "viz": {
                "graph.dimensions": ["Classification Ladder Tier"],
                "graph.metrics": ["Items Classified"],
                "graph.colors": ["#845EC2"]
            },
            "grid": (0, 19, 24, 7)
        }
    ]

    for item in d4_cards:
        cid = create_or_update_card(cur, item["name"], item["desc"], item["display"], item["sql"], item["viz"], c_ops)
        col, row, sx, sy = item["grid"]
        place_card_on_dashboard(cur, d4_id, cid, col, row, sx, sy, item["viz"])

    conn.commit()
    conn.close()
    print("\n=============================================================================")
    print("SUCCESS: 4 Comprehensive Dashboards & 38 Analytical Questions Created in Metabase!")
    print(f"  1. Cambodia National Inflation & Macroeconomic CPI Observatory (ID: {d1_id})")
    print(f"  2. UN COICOP Division & Price Dynamics Deep-Dive (ID: {d2_id})")
    print(f"  3. Retailer Competition, Cross-Store Dispersion & Promotion Analytics (ID: {d3_id})")
    print(f"  4. Scraper Operations, Data Pipeline Health & Anomaly Triage (ID: {d4_id})")
    print("Metabase URL: http://localhost:3000")
    print("=============================================================================")

if __name__ == "__main__":
    provision_all()
