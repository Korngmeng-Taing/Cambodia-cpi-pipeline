# Cambodia National Consumer Price Index (CPI) Pipeline Architecture

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

### 3. Silver Layer: Clean Core & Intelligence
- **Python RapidFuzz Entity Matching:** Deduplicates products across stores into canonical UUID5 identities (`silver.canonical_items`, `silver.item_match_log`).
- **dbt Price Cleaning & Unit Standardization:** Converts USD $\to$ KHR via MEF rates, clamps discounts ($0\%$–$95\%$), standardizes unit prices (`KHR/kg`, `KHR/L`), and flags outliers.
- **Gemini AI COICOP Classifier:** 9-tier daily-scoped division ladder (Exact/per-store overrides $\to$ Store purity $\to$ AI cache with store-context gate $\to$ Global overrides $\to$ Traps with personal-care guard $\to$ Keyword STRONG rules (`coicop_keywords.csv`, priority <300) $\to$ Category map $\to$ Keyword WEAK rules + store defaults). Cached answers are pre-warmed into `silver.dim_coicop_ai_cache` (~30,800 products across 82 unique 5-digit COICOP 2018 classes).
- **Hedonic Quality Adjustments:** Constant-specification regression (`silver.hedonic_adjusted_prices`) holding RAM/Storage constant for Division 09/08 consumer electronics.
- **Conformed Star Schema & Analytical Views:**
  - `silver.dim_items` (Master product catalog)
  - `silver.dim_stores` (20 Cambodian retailers/sources)
  - `silver.fct_daily_prices` (Clean daily price observations)
  - `silver.hedonic_adjusted_prices` (Constant-specification quality adjusted prices)
  - `silver.fct_jevons_daily` (Elementary Jevons store-unweighted geometric mean prices $P_{\text{Jevons}}$)
  - `silver.classification_queue` (Active triage queue for unclassified products)

### 4. Gold Layer: Econometric Engine & 12 Division Tables
- **Strict 2-Stage Sequence (Jevons $\to$ Laspeyres):**
  1. **Stage 1 (Elementary Jevons & Imputation):** Unweighted geometric mean price per canonical item across all stores (`gold.fct_daily_price_stats`). Missing products ($\le 7$ days) receive **Class-Mean Imputation** (ILO standard) based on division geometric movement.
  2. **Stage 2 (Higher-Level Laspeyres):** Category and headline weighted roll-up using official Cambodia NIS 2004 expenditure weights (`gold.cpi_category_daily`, `gold.cpi_headline_daily`) with dynamic $100.000\%$ reweighting.
- **12 Dedicated Division Analytical Tables:**
  - `gold.cpi_div01_food` through `gold.cpi_div12_misc` exposing full item-level price trends, base indices, and metrics per division.
- **Advanced Econometrics:**
  - **Multilateral GEKS-Törnqvist:** 13-period rolling window transitive index with Movement Splicing (`gold.cpi_geks_multilateral`).
  - **Superlative Fisher Ideal Index:** Measures consumer substitution bias ($\text{Bias} = I_{\text{Laspeyres}} - I_{\text{Fisher}}$).
  - **Operational Anomaly Detection:** Single-pass `LAG()` window identifying $>15\%$ price shocks and promo shifts (`gold.mart_price_anomalies`).

### 5. Serving & BI
- **Metabase Executive Dashboards (:3000):** Visual charts for headline CPI, 12 COICOP division indices, inflation curves, top movers, and promo depth.
- **Streamlit Human Review UI (:8501):** Human-in-the-loop triage for low-confidence matches and review queues.

### 6. Airflow 2.9.3 Master Orchestration Flow
```
start_cpi_pipeline
  ──► [20 Scraper DAGs in Parallel]
  ──► bronze_layer_complete (Barrier Gate)
  ──► trigger_silver_dag (Item Matching + dbt Silver)
  ──► silver_layer_complete (Barrier Gate)
  ──► trigger_coicop_classification_dag (Gemini AI Classification)
  ──► coicop_layer_complete (Barrier Gate)
  ──► trigger_gold_dag (sp_calculate_daily_cpi + dbt Gold Models & DQ Tests)
  ──► cpi_pipeline_success
```
