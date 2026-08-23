# Cambodia Daily CPI Pipeline — Metabase BI Dashboard Suite Blueprint

This document details the architecture, visual design, mathematical formulas, and SQL definitions of the **Metabase BI Dashboard Suite** for the Cambodia Daily Consumer Price Index (CPI) Medallion Pipeline.

The dashboard suite is hosted live on **Metabase (Port 3000)** connected to the **PostgreSQL 16 Data Warehouse (`cpi_db`)**.

---

## 1. Executive Dashboard Matrix & Architecture

The analytics suite is organized into **4 specialized dashboards** covering executive macroeconomic tracking, division-level price dynamics, retail market competitiveness, and data engineering observability.

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 CAMBODIA CPI METABASE DASHBOARD SUITE                                  │
├────────────────────────────────┬────────────────────────────────┬──────────────────────────────────────┤
│ Dashboard Name                 │ Target Audience                │ Key Focus & Metrics                  │
├────────────────────────────────┼────────────────────────────────┼──────────────────────────────────────┤
│ 1. Cambodia National Inflation │ Central Bank / MEF / Economists│ • Headline Laspeyres vs GEKS Index   │
│    & Macro Observatory         │ Executives & Policy Makers     │ • DoD & MoM Inflation Momentum      │
│                                │                                │ • Substitution Bias & Fisher Index   │
│                                │                                │ • Official USD/KHR MEF Exchange Rate │
├────────────────────────────────┼────────────────────────────────┼──────────────────────────────────────┤
│ 2. UN COICOP Division &        │ Category Managers / Sector     │ • 12 UN COICOP Division Trajectories │
│    Price Dynamics Deep-Dive    │ Analysts / Commodity Traders   │ • Top 15 Inflation & Deflation Items │
│                                │                                │ • Item-Level Jevons Price Explorer   │
│                                │                                │ • Unit Price Standardized Tracking   │
├────────────────────────────────┼────────────────────────────────┼──────────────────────────────────────┤
│ 3. Retailer Competition,       │ Retail Commercial Teams        │ • Identical Item Price Dispersion    │
│    Cross-Store Dispersion &    │ Supermarket Merchandisers      │ • Retailer Price Leadership Leaderboard│
│    Promotion Analytics         │                                │ • Promotional Catalog Penetration %  │
│                                │                                │ • Consumer Promotional Savings Depth │
├────────────────────────────────┼────────────────────────────────┼──────────────────────────────────────┤
│ 4. Scraper Operations, Data    │ Data Engineers / MLOps /       │ • 20-Source Scraper Availability Grid│
│    Pipeline Health & Triage    │ SRE Site Reliability           │ • Daily Ingestion Volume (14-Day)    │
│                                │                                │ • Price Anomaly & Extreme Surge Feed │
│                                │                                │ • Hybrid AI/Rule Classification Log │
└────────────────────────────────┴────────────────────────────────┴──────────────────────────────────────┘
```

---

## 2. Dashboard 1: Cambodia National Inflation & Macro Observatory

* **Collection:** `01 - Cambodia Executive Inflation Observatory`
* **Metabase URL:** [http://localhost:3000/dashboard/4](http://localhost:3000/dashboard/4)

### 2.1 Visual Grid Layout (24-Column Grid)

```
┌─────────────────┬─────────────────┬─────────────────┬─────────────────┬─────────────────┬─────────────────┐
│ Headline CPI    │ DoD Inflation   │ MoM Inflation   │ GEKS Multilat.  │ Substitution    │ USD/KHR FX Rate │
│ (Base 100)      │ Rate (%)        │ Rate (%)        │ Index           │ Bias (bps)      │ (MEF Official)  │
│ [4x3] (0,0)     │ [4x3] (4,0)     │ [4x3] (8,0)     │ [4x3] (12,0)    │ [4x3] (16,0)    │ [4x3] (20,0)    │
├─────────────────┴─────────────────┴────────┬────────┴─────────────────┴─────────────────┴─────────────────┤
│ National Headline CPI Trajectory           │ Inflation Momentum Dynamics                                  │
│ (Laspeyres vs GEKS vs Core vs USD CPI)     │ (Day-on-Day vs Month-on-Month % Trajectory)                  │
│ [14x8] (0,3)                               │ [10x8] (14,3)                                                │
├────────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ 12 UN COICOP Division Weights & Indices    │ Superlative Fisher Ideal vs Laspeyres vs Paasche             │
│ [14x8] (0,11)                              │ [10x8] (14,11)                                               │
├────────────────────────────────────────────┴──────────────────────────────────────────────────────────────┤
│ National Daily CPI Audit & Imputation History Table                                                       │
│ [24x7] (0,19)                                                                                             │
└───────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Card Catalog & SQL Definitions

#### Card 1.1: Headline CPI (Laspeyres Base=100) [Scalar]
```sql
SELECT cpi_headline_khr AS "Headline CPI (KHR)" 
FROM gold.mart_cpi_daily 
ORDER BY scrape_date DESC 
LIMIT 1;
```

#### Card 1.2: Day-on-Day Inflation Rate (%) [Scalar]
```sql
SELECT inflation_dod_pct AS "DoD Inflation (%)" 
FROM gold.mart_cpi_daily 
ORDER BY scrape_date DESC 
LIMIT 1;
```

#### Card 1.3: Month-on-Month Inflation Rate (%) [Scalar]
```sql
SELECT inflation_mom_pct AS "MoM Inflation (%)" 
FROM gold.mart_cpi_daily 
ORDER BY scrape_date DESC 
LIMIT 1;
```

#### Card 1.4: Multilateral GEKS-Törnqvist Index [Scalar]
```sql
SELECT cpi_geks_multilateral AS "GEKS Multilateral CPI" 
FROM gold.mart_cpi_daily 
ORDER BY scrape_date DESC 
LIMIT 1;
```

#### Card 1.5: Consumer Substitution Bias (%) [Scalar]
```sql
SELECT substitution_bias_pct AS "Substitution Bias (%)" 
FROM gold.cpi_fisher_superlative 
ORDER BY scrape_date DESC 
LIMIT 1;
```

#### Card 1.6: MEF USD / KHR Official Rate [Scalar]
```sql
SELECT usd_khr_exchange_rate AS "USD/KHR Rate" 
FROM gold.v_monitor_fx_health 
ORDER BY execution_date DESC 
LIMIT 1;
```

#### Card 1.7: National Headline CPI Trajectory (Time-Series Multi-Line) [Line Chart]
```sql
SELECT 
    scrape_date,
    cpi_headline_khr AS "Laspeyres Headline",
    cpi_geks_multilateral AS "GEKS-Tornqvist Multilateral",
    cpi_core_khr AS "Core CPI (Excl Food & Energy)",
    cpi_headline_usd AS "USD Denominated CPI"
FROM gold.mart_cpi_daily
ORDER BY scrape_date ASC;
```

#### Card 1.8: Inflation Momentum (DoD vs MoM %) [Line Chart]
```sql
SELECT 
    scrape_date,
    inflation_dod_pct AS "Day-on-Day (%)",
    inflation_mom_pct AS "Month-on-Month (%)"
FROM gold.mart_cpi_daily
ORDER BY scrape_date ASC;
```

#### Card 1.9: 12 UN COICOP Division Weights & Current Indices [Table]
```sql
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
```

#### Card 1.10: Superlative Fisher Ideal vs Laspeyres Index [Line Chart]
```sql
SELECT 
    scrape_date,
    laspeyres_index AS "Laspeyres Index",
    paasche_index AS "Paasche Index",
    fisher_index AS "Fisher Superlative",
    substitution_bias_pct AS "Substitution Bias (%)"
FROM gold.cpi_fisher_superlative
ORDER BY scrape_date ASC;
```

#### Card 1.11: National Daily CPI Audit History [Table]
```sql
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
```

---

## 3. Dashboard 2: UN COICOP Division & Price Dynamics Deep-Dive

* **Collection:** `02 - UN COICOP Division & Price Dynamics`
* **Metabase URL:** [http://localhost:3000/dashboard/5](http://localhost:3000/dashboard/5)

### 3.1 Visual Grid Layout (24-Column Grid)

```
┌──────────────────────────┬──────────────────────────┬──────────────────────────┬──────────────────────────┐
│ Food & Non-Alcoholic     │ Housing & Utilities      │ Transport & Fuel         │ Health & Medical         │
│ (Div 01 - 44.8% Weight)  │ (Div 04 - 17.1% Weight)  │ (Div 07 - 12.2% Weight)  │ (Div 06 - 5.6% Weight)   │
│ [6x3] (0,0)              │ [6x3] (6,0)              │ [6x3] (12,0)             │ [6x3] (18,0)             │
├──────────────────────────┴───────────────┬──────────┴──────────────────────────┴──────────────────────────┤
│ All 12 COICOP Divisions Daily Trajectory │ Division Inflation Contribution to Headline CPI                │
│ [14x8] (0,3)                             │ [10x8] (14,3)                                                  │
├──────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
│ Top 15 High-Inflation Commodity Spikes   │ Top 15 Deflationary Items / Price Drops                        │
│ [12x8] (0,11)                            │ [12x8] (12,11)                                                 │
├──────────────────────────────────────────┴────────────────────────────────────────────────────────────────┤
│ Tracked Item Quotes & Stores per Division Bar Chart [24x7] (0,19)                                         │
├───────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Granular Product-Level Price Explorer (Jevons Price, Base Price & Base Index) [24x8] (0,26)               │
└───────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Card Catalog & SQL Definitions

#### Card 2.1: Division 01 Food & Beverages Index [Scalar]
```sql
SELECT division_index_khr 
FROM gold.mart_cpi_division_daily 
WHERE coicop_division = '01' 
ORDER BY scrape_date DESC 
LIMIT 1;
```

#### Card 2.2: Division 04 Housing & Utilities Index [Scalar]
```sql
SELECT division_index_khr 
FROM gold.mart_cpi_division_daily 
WHERE coicop_division = '04' 
ORDER BY scrape_date DESC 
LIMIT 1;
```

#### Card 2.3: Division 07 Transport Index [Scalar]
```sql
SELECT division_index_khr 
FROM gold.mart_cpi_division_daily 
WHERE coicop_division = '07' 
ORDER BY scrape_date DESC 
LIMIT 1;
```

#### Card 2.4: Division 06 Health Index [Scalar]
```sql
SELECT division_index_khr 
FROM gold.mart_cpi_division_daily 
WHERE coicop_division = '06' 
ORDER BY scrape_date DESC 
LIMIT 1;
```

#### Card 2.5: All 12 COICOP Divisions Daily Inflation Trajectory [Line Chart]
```sql
SELECT 
    scrape_date,
    coicop_division || ' - ' || division_name AS division_label,
    division_index_khr AS index_value
FROM gold.mart_cpi_division_daily
ORDER BY scrape_date ASC, coicop_division ASC;
```

#### Card 2.6: Division Inflation Contribution to Headline CPI [Bar Chart]
```sql
SELECT 
    division_name AS "Division",
    ROUND(weight_pct * (division_index_khr - 100.0) / 100.0, 3) AS "Inflation Contribution (pts)"
FROM gold.mart_cpi_division_daily
WHERE scrape_date = (SELECT MAX(scrape_date) FROM gold.mart_cpi_division_daily)
ORDER BY "Inflation Contribution (pts)" DESC;
```

#### Card 2.7: Top 15 High-Inflation Commodity Spikes [Table]
```sql
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
```

#### Card 2.8: Top 15 Deflationary Items / Price Drops [Table]
```sql
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
```

#### Card 2.9: Tracked Item Quotes & Stores per Division [Bar Chart]
```sql
SELECT 
    coicop_division || ' - ' || division_name AS "Division",
    active_items_count AS "Active Items Tracked",
    stores_count AS "Retailers Quoting"
FROM gold.mart_cpi_division_daily
WHERE scrape_date = (SELECT MAX(scrape_date) FROM gold.mart_cpi_division_daily)
ORDER BY active_items_count DESC;
```

#### Card 2.10: Granular Product-Level Price Explorer [Table]
```sql
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
```

---

## 4. Dashboard 3: Retailer Competition, Cross-Store Dispersion & Promotion Analytics

* **Collection:** `03 - Retailer Competition & Promo Analytics`
* **Metabase URL:** [http://localhost:3000/dashboard/6](http://localhost:3000/dashboard/6)

### 4.1 Visual Grid Layout (24-Column Grid)

```
┌──────────────────────────┬──────────────────────────┬──────────────────────────┬──────────────────────────┐
│ Catalog Promo            │ Average Discount Depth   │ Promotional Deflation    │ Cross-Store Matched      │
│ Penetration Rate (%)     │ on Discounted Items (%)  │ Savings Passed On (%)    │ Identical Products Count │
│ [6x3] (0,0)              │ [6x3] (6,0)              │ [6x3] (12,0)             │ [6x3] (18,0)             │
├──────────────────────────┴───────────────┬──────────┴──────────────────────────┴──────────────────────────┤
│ Identical Item Cross-Store Dispersion    │ Retailer Price Competitiveness Leaderboard                     │
│ (Cheapest vs Most Expensive Retailer)    │ (Share of lowest price market offerings)                       │
│ [14x9] (0,3)                             │ [10x9] (14,3)                                                  │
├──────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
│ Promotional Activity by Retailer Table   │ Promotional Share by COICOP Division Bar Chart                 │
│ [12x8] (0,12)                            │ [12x8] (12,12)                                                 │
└──────────────────────────────────────────┴────────────────────────────────────────────────────────────────┘
```

### 4.2 Card Catalog & SQL Definitions

#### Card 3.1: Catalog Promo Penetration (%) [Scalar]
```sql
SELECT ROUND(AVG(promo_penetration_pct), 2) AS "Promo Penetration (%)" 
FROM silver.v_promo_analytics 
WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.v_promo_analytics);
```

#### Card 3.2: Average Promotional Discount Depth (%) [Scalar]
```sql
SELECT ROUND(AVG(avg_discount_pct), 2) AS "Avg Discount Depth (%)" 
FROM silver.v_promo_analytics 
WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.v_promo_analytics) 
  AND avg_discount_pct IS NOT NULL;
```

#### Card 3.3: Promotional Deflation Savings (%) [Scalar]
```sql
SELECT ROUND(AVG(promo_deflation_savings_pct), 2) AS "Consumer Savings (%)" 
FROM silver.v_promo_analytics 
WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.v_promo_analytics);
```

#### Card 3.4: Cross-Store Matched Identical Products [Scalar]
```sql
SELECT COUNT(DISTINCT item_id) AS "Multi-Store Items" 
FROM silver.v_cross_store_dispersion 
WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.v_cross_store_dispersion);
```

#### Card 3.5: Identical Item Cross-Store Price Dispersion [Table]
```sql
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
```

#### Card 3.6: Retailer Price Competitiveness Leaderboard [Bar Chart]
```sql
SELECT 
    cheapest_store AS "Retailer",
    COUNT(*) AS "Lowest Price Quotes",
    ROUND(COUNT(*)::NUMERIC / SUM(COUNT(*)) OVER () * 100.0, 1) AS "Market Price Leadership (%)"
FROM silver.v_cross_store_dispersion
WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.v_cross_store_dispersion)
GROUP BY cheapest_store
ORDER BY "Lowest Price Quotes" DESC;
```

#### Card 3.7: Promotional Activity by Retailer [Table]
```sql
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
```

#### Card 3.8: Promotional Share by COICOP Division [Bar Chart]
```sql
SELECT 
    coicop_division AS "COICOP Division",
    SUM(promo_items_count) AS "Promotional Items",
    ROUND(AVG(promo_penetration_pct), 1) AS "Promo Penetration (%)"
FROM silver.v_promo_analytics
WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.v_promo_analytics)
GROUP BY coicop_division
ORDER BY "Promotional Items" DESC;
```

---

## 5. Dashboard 4: Scraper Operations, Pipeline Health & Anomaly Triage

* **Collection:** `04 - Scraper Operations & Data Ops`
* **Metabase URL:** [http://localhost:3000/dashboard/7](http://localhost:3000/dashboard/7)

### 5.1 Visual Grid Layout (24-Column Grid)

```
┌──────────────────────────┬──────────────────────────┬──────────────────────────┬──────────────────────────┐
│ Online Scrapers Count    │ Today Ingested Items     │ Official MEF FX Rate     │ Flagged Price Anomalies  │
│ (20-Source Registry)     │ (Atomic Observations)    │ (USD/KHR Daily)          │ (>20% Shift Alerts)      │
│ [6x3] (0,0)              │ [6x3] (6,0)              │ [6x3] (12,0)             │ [6x3] (18,0)             │
├──────────────────────────┴───────────────┬──────────┴──────────────────────────┴──────────────────────────┤
│ 20-Source Scraper Availability Matrix    │ Daily Ingested Volume by Store (Last 14 Days)                  │
│ [14x8] (0,3)                             │ [10x8] (14,3)                                                  │
├──────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
│ Real-Time Price Anomaly & Shift Feed     │ Pipeline Quality, Barcode & Imputation Guardrails              │
│ [14x8] (0,11)                            │ [10x8] (14,11)                                                 │
├──────────────────────────────────────────┴────────────────────────────────────────────────────────────────┤
│ Hybrid COICOP Classification Pipeline Throughput Funnel [24x7] (0,19)                                     │
└───────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Card Catalog & SQL Definitions

#### Card 4.1: Online Scrapers Count (20-Source Registry) [Scalar]
```sql
SELECT COUNT(*) AS "Online Scrapers" 
FROM gold.v_monitor_source_health_matrix 
WHERE pipeline_health IN ('ONLINE_FRESH', 'ONLINE_YESTERDAY');
```

#### Card 4.2: Today Total Ingested Items [Scalar]
```sql
SELECT SUM(total_items_scraped) AS "Total Items Today" 
FROM gold.v_monitor_scraper_daily 
WHERE scrape_date = (SELECT MAX(scrape_date) FROM gold.v_monitor_scraper_daily);
```

#### Card 4.3: MEF Official USD/KHR Rate [Scalar]
```sql
SELECT usd_khr_exchange_rate 
FROM gold.v_monitor_fx_health 
ORDER BY execution_date DESC 
LIMIT 1;
```

#### Card 4.4: Flagged Price Anomaly Alerts (>20% Shift) [Scalar]
```sql
SELECT COUNT(*) AS "Anomaly Alerts" 
FROM gold.v_monitor_price_alerts 
WHERE scrape_date = (SELECT MAX(scrape_date) FROM gold.v_monitor_price_alerts);
```

#### Card 4.5: 20-Source Scraper Availability Matrix [Table]
```sql
SELECT 
    store_slug AS "Source / Store Slug",
    latest_scrape_date AS "Latest Ingestion Date",
    days_since_last_scrape AS "Lag (Days)",
    avg_daily_volume_7d AS "7D Avg Volume",
    active_days_last_7d AS "Active Days (7D)",
    pipeline_health AS "Operational Status"
FROM gold.v_monitor_source_health_matrix
ORDER BY days_since_last_scrape ASC, avg_daily_volume_7d DESC;
```

#### Card 4.6: Daily Ingested Volume by Store (Last 14 Days) [Stacked Bar Chart]
```sql
SELECT 
    scrape_date,
    store_slug,
    total_items_scraped
FROM gold.v_monitor_scraper_daily
WHERE scrape_date >= CURRENT_DATE - INTERVAL '14 days'
ORDER BY scrape_date ASC, store_slug ASC;
```

#### Card 4.7: Real-Time Price Anomaly & Extreme Shift Feed [Table]
```sql
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
```

#### Card 4.8: Pipeline Quality & Coverage Guardrails [Table]
```sql
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
```

#### Card 4.9: Hybrid COICOP Classification Pipeline Throughput [Bar Chart]
```sql
SELECT 
    coicop_method AS "Classification Ladder Tier",
    COUNT(*) AS "Items Classified",
    ROUND(COUNT(*)::NUMERIC / SUM(COUNT(*)) OVER () * 100.0, 1) AS "Share (%)"
FROM silver.fct_daily_prices
WHERE scrape_date = (SELECT MAX(scrape_date) FROM silver.fct_daily_prices)
  AND coicop_method IS NOT NULL
GROUP BY coicop_method
ORDER BY "Items Classified" DESC;
```

---

## 6. How to Rebuild, Customize, or Provision Dashboards

To re-run automated provisioning or update all Metabase questions with new queries:

```bash
# Execute the automated dashboard provisioner
python scripts/setup_metabase_dashboards.py
```

### Accessing Metabase
1. Open your browser and navigate to: **`http://localhost:3000`**
2. Login with:
   * **Email:** `korngmeng015@gmail.com`
   * **Password:** *(Your configured Metabase master password)*
3. Navigate to **Collections** to see all 4 organized suites and dashboards.
