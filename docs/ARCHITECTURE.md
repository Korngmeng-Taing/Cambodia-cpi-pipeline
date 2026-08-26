# Cambodia National Consumer Price Index (CPI) Pipeline Architecture

> **[!WARNING]**
> **IMPLEMENTATION STATUS (2026-08):** The Gold-layer index computation described in parts of this document - Jevons elementary aggregates, imputation, Laspeyres category/headline roll-ups, GEKS-Tornqvist, Fisher Ideal - is **planned but NOT implemented yet**. Its calculators, dbt models, and gold tables were removed from the codebase.
> Currently live: Bronze ingestion; Silver cleaning / item matching / AI classification / hedonic adjustment; Gold star schema (dim_items, dim_stores, fct_daily_prices); monitoring views. See README "Implementation Status".

![Cambodia National Consumer Price Index (CPI) Simple Architecture](./cpi_simple_architecture.jpg)

![Cambodia CPI Tech Stack Overview](./cpi_tech_stack.jpg)

---

## 1. End-to-End Architectural Flow

The pipeline executes daily across 5 interconnected layers:

### 1. 20 Scraper Sources
- **Retail & E-commerce:** AEON 1 Phnom Penh, AEON 3 Mean Chey, Delishop Cambodia, L192 Marketplace.
- **Healthcare & Consumer Tech:** Community Pharmacy, Khmer Samnang Phone Shop, Ary Store Phone.
- **Telecom & Housing:** Cellcard Mobile & WiFi, Smart Mobile & WiFi, Khmer24 Real Estate, Realestate.com.kh.
- **Intercity Transport & Travel:** redBus Cambodia (Multi-Operator Portal), BookMeBus Cambodia (Multi-Operator Booking Platform).
- **Hospitality & Dining:** Sokha Phnom Penh Hotel, Hyatt Regency Phnom Penh, Bayon Restaurant BKK I.
- **Macroeconomic Fuel & Official FX:** MOC Petroleum Gasoline (Live GraphQL), Ministry of Economy & Finance (MEF USD/KHR official daily rate).

### 2. Bronze & Staging Layer
- **PostgreSQL Staging (`staging.raw_scrapes`):** Append-only raw JSONB payloads with unique `run_id`.
- **Bronze Raw Price Observations (`bronze.raw_prices`):** Typed raw price observations (~35,000 listings/day).
- **dbt Staging Views (`stg_raw_scrapes`):** Unpacks JSONB into structured columns with zero-product quality gates.

### 3. Silver Layer: Store-Level Cleaned Tables (1 Store 1 Table)
- **Python RapidFuzz & Trigram Entity Matching:** Deduplicates products across stores into canonical UUID identities (`silver.canonical_items`, `silver.item_match_log`) backed by a PostgreSQL `pg_trgm` GIN index (`idx_canonical_name_trgm`) and automated Rule Guard spec evaluation.
- **dbt Price Cleaning & Unit Standardization:** Converts USD $\to$ KHR via MEF rates, clamps discounts ($0\%$–$95\%$), standardizes unit prices (`KHR/kg`, `KHR/L`), and flags outliers.
- **Gemini AI COICOP Classifier:** Streamlined 4-tier daily-scoped division ladder (Exact/per-store overrides $\to$ Store domain purity $\to$ Global overrides $\to$ High-throughput Gemini AI memoized cache in `silver.dim_coicop_ai_cache` $\to$ Native category map / Fallback queue). Over 99% of daily products resolve from cache in 0ms with >98% semantic accuracy.
- **Multi-Feature Hedonic Quality Adjustments:** Constant-specification regression (`silver.hedonic_adjusted_prices`) holding RAM, Storage, Screen Size, Camera MP, and 5G connectivity constant for Division 09/08 consumer electronics.
- **Clean Store Observations & Operational Tables (1 Store 1 Table Paradigm):**
  - `silver.clean_store_prices` (Standardized daily price quotes partitioned per store and source)
  - `silver.canonical_items` (Canonical identity registry with GIN trigram index)
  - `silver.item_match_log` (Automated item matching audit log)
  - `silver.needs_review` (Borderline matching review queue evaluated by Rule Guard + Gemini AI)
  - `silver.dim_coicop_ai_cache` (Persistent classification cache)
  - `silver.classification_queue` (Active triage queue for unclassified products)

### 4. Gold Layer: Conformed Star Schema & Econometric Engine
- **Conformed Dimensional Star Schema:**
  - `gold.dim_items` (Master canonical product dimension)
  - `gold.dim_stores` (Conformed retailer and provider dimension)
  - `gold.fct_daily_prices` (Conformed daily price facts at `(scrape_date, store_slug, item_id)` grain)
  - `gold.fct_daily_prices_imputed` (Imputed price facts with forward carry $\le 7$ days)
  - `gold.fct_jevons_daily` (Elementary Jevons unweighted geometric mean price facts $P_{\text{Jevons}}$)
- **Strict 2-Stage Sequence (Jevons $\to$ Laspeyres):**
  1. **Stage 1 (Elementary Jevons & Imputation):** Unweighted geometric mean price per canonical item across all stores (`gold.fct_jevons_daily`). Missing products receive **Class-Mean Imputation** (ILO standard).
  2. **Stage 2 (Higher-Level Laspeyres):** Category and headline weighted roll-up using official Cambodia NIS 2004 expenditure weights (`gold.cpi_category_daily`, `gold.cpi_headline_daily`) with dynamic $100.000\%$ reweighting.
- **12 Dedicated Division Analytical Tables:**
  - `gold.cpi_div01_food` through `gold.cpi_div12_misc` exposing full item-level price trends, base indices, and metrics per division.
- **Advanced Econometrics:**
  - **Multilateral GEKS-Törnqvist:** 13-period rolling window transitive index with Movement Splicing (`gold.cpi_geks_multilateral`).
  - **Superlative Fisher Ideal Index:** Measures consumer substitution bias ($\text{Bias} = I_{\text{Laspeyres}} - I_{\text{Fisher}}$).
  - **Operational Anomaly Detection:** Single-pass `LAG()` window identifying $>15\%$ price shocks and promo shifts (`gold.mart_price_anomalies`).

### 5. Serving & BI
- **Metabase Executive Dashboards (:3000):** Visual charts for headline CPI, 12 COICOP division indices, inflation curves, top movers, and promo depth.
- **Metabase Analytics & BI (:3000):** Real-time operational monitoring, 20-source scraper health matrix, and analytical dashboards.

### 6. Airflow Master Orchestration Flow
```
start_cpi_pipeline
  ──► [20 Scraper DAGs in Parallel]
  ──► bronze_layer_complete (Barrier Gate)
  ──► verify_bronze_minimum_success (Data Quality Gate)
  ──► trigger_silver_dag (Item Matching + AI Cache Pre-Warm + Hedonic + dbt Silver)
  ──► silver_layer_complete (Barrier Gate)
  ──► trigger_gold_dag (dbt Gold Models & DQ Tests + Serving Views)
  ──► gold_layer_complete
  ──► cpi_pipeline_success
```
