# Updated Methodology & Activity Plan
# Automated Price Collection for CPI and Inflation Estimation

**Project:** Cambodia National Consumer Price Index (CPI) Pipeline  
**Target:** Thesis Chapter 3 (Methodology & Implementation Activities)  
**Architecture:** Medallion Data Architecture (PostgreSQL 16 + Airflow + dbt Core + Gemini/Ollama AI + ML Forecasting + Metabase/Streamlit)  

---

## Overview of Upgrades from Initial Proposal to Week 3

| Component | Initial Proposal | Week 3 Upgraded Architecture |
| :--- | :--- | :--- |
| **Category Scope** | 5 Selected Categories | **Full 12 COICOP Divisions** (100.000% National Basket Coverage) |
| **Data Storage** | Object Storage Buckets (MinIO) | **Medallion Star-Schema** in PostgreSQL 16 (`bronze.*`, `silver.*`, `gold.*`) |
| **Classification** | Basic Keyword / Simple NLP | **7-Tier Hybrid Cascade** (Source Pinning $\to$ Overrides $\to$ AI Cache $\to$ Regex Ladder $\to$ Gemini Flash $\to$ Local Ollama Fallback $\to$ Human Triage) |
| **CPI Calculation** | 1-Stage Simple Laspeyres | **Official 2-Stage Aggregation** (Stage 1 Elementary Jevons $\to$ Stage 2 Laspeyres with NIS Weights + 13-period Multilateral GEKS) |
| **Serving & UI** | Single Streamlit App | **Dual-Engine UI** (Metabase BI on `:3000` + Streamlit Human Triage & ML Forecast UI on `:8501`) |

---

## Phase 1: Data Infrastructure, Ingestion, Preprocessing & Classification

*This phase establishes the automated data pipeline, raw storage, entity resolution, and AI classification.*

### 1.1 Infrastructure Setup
- Configure **Apache Airflow 2.9.3** for daily DAG scheduling, dependency management, and quality barriers.
- Implement the **Medallion Architecture** inside **PostgreSQL 16**:
  - **Bronze Layer (`staging.raw_scrapes`, `bronze.raw_prices`):** Append-only raw JSONB payloads with unique `run_id`, scraped timestamps, and currency markers.
  - **Silver Layer (`silver.*`):** Conformed dimensional tables (`dim_items`, `dim_stores`) and price facts (`fct_daily_prices`).
  - **Gold Layer (`gold.*`):** Analytical marts and high-frequency CPI indices.

### 1.2 Automated Web Scraping (Multi-Source Ingestion)
- Develop modular Python scrapers using `httpx`, `BeautifulSoup4`, `Playwright`, and live GraphQL APIs across **20 Cambodian market sources**:
  - **Supermarkets & Grocery:** AEON 1, AEON 3, DeliShop Cambodia, L192 Marketplace (Divisions 01, 02, 05, 09, 10, 12).
  - **Healthcare & Pharmacy:** Community Pharmacy (Division 06).
  - **Electronics & Phones:** Khmer Samnang, Ary Store (Divisions 08, 09).
  - **Telecom & Internet:** Cellcard, Smart Axiata (Division 08).
  - **Housing & Rentals:** Khmer24 Real Estate, Realestate.com.kh, utility tariffs (Division 04).
  - **Intercity Transport:** redBus Cambodia, BookMeBus (Division 07).
  - **Hospitality & Dining:** Sokha Hotel, Hyatt Regency, Bayon Restaurant (Division 11).
  - **Fuel & FX:** Ministry of Commerce (MOC) Gasoline live API, Ministry of Economy & Finance (MEF) Official FX API (Divisions 07, 12).

### 1.3 Preprocessing, Normalization & Entity Matching (Silver Layer)
- **Text Distillation (`text_clean.py`):** Strips marketing noise (`SALE`, `HOT DEAL`, `PROMOTION`), normalizes Khmer numerals (`០–៩` $\to$ `0–9`), and translates core food/commodity nouns.
- **Unit Standardization:** Parses weights/volumes (`500g`, `1.5L`) into standardized unit rates (`KHR/kg`, `KHR/L`) to neutralize shrinkflation distortions.
- **Single-Point FX Conversion:** Converts USD prices to KHR using daily official MEF rates.
- **Entity Resolution (`item_matcher.py`):** Uses RapidFuzz Token-Sort fuzzy matching ($\ge 0.95$) and size compatibility checks to deduplicate quotes across retailers into canonical UUID identities (`silver.canonical_items`).

### 1.4 7-Tier Hybrid COICOP Classification Engine
- **Tier 1 (Source Pinning):** Direct mapping for single-purpose channels (Khmer24 $\to$ Div 04, redBus $\to$ Div 07, MOC $\to$ Div 07).
- **Tier 2 (Manual Overrides):** Curated ground-truth rules (`dbt/seeds/coicop_override.csv`).
- **Tier 3 (Postgres AI Cache):** Instant sub-millisecond lookup in `silver.dim_coicop_ai_cache` for previously classified strings.
- **Tier 4 (Word-Boundaried Regex Ladder):** Safe precedence ordering (Div 12 $\to$ 02 $\to$ 05 $\to$ ... $\to$ 01) preventing personal care goods from being stolen by food rules.
- **Tier 5 (Cloud LLM - Gemini Flash):** Batches of 50 unclassified products processed with structured JSON mode.
- **Tier 6 (Local Offline LLM - Ollama Qwen 2.5 7B):** Local fallback ensuring zero rate limits and continuous offline execution during API outages.
- **Tier 7 (Human-in-the-Loop Triage):** Low-confidence items ($< 0.50$) route to `silver.classification_queue` and the Streamlit review dashboard.

---

## Phase 2: Exploratory Data Analysis & 12 COICOP Category Visualization

*This phase focuses on weight assignment, visual validation, and price distribution analytics across the consumer basket.*

### 2.1 Weight Assignment & Basket Calibration
- Calibrate the consumer basket using the official **Cambodia National Institute of Statistics (NIS) 2004 Household Expenditure Survey weights**, normalized across all 12 COICOP divisions to exactly $100.000\%$:
  - Div 01 Food & Beverages: $44.800\%$
  - Div 04 Housing & Utilities: $18.400\%$
  - Div 07 Transport: $8.900\%$
  - Div 11 Restaurants & Hotels: $6.200\%$
  - Div 06 Health: $5.300\%$
  - Div 08 Communication: $4.100\%$
  - Div 03 Clothing: $3.700\%$
  - Div 05 Furnishings: $3.500\%$
  - Div 12 Miscellaneous: $2.600\%$
  - Div 02 Alcohol & Tobacco: $1.300\%$
  - Div 09 Recreation: $0.900\%$
  - Div 10 Education: $0.300\%$

### 2.2 Exploratory Visualization & Validation
- **High-Frequency Trend Tracking:** Daily/weekly time-series line charts tracking price indices across all 12 divisions.
- **Volatility & Outlier Analysis:** Box plots and rolling volatility heatmaps identifying volatile commodities (e.g., fresh pork, gasoline, intercity transit).
- **Weight & Expenditure Treemaps:** Interactive hierarchical treemaps visualizing the relative expenditure shares of divisions, groups, and classes.
- **Classification Coverage Validation:** Coverage audits (`gold.v_coverage`) verifying the percentage of daily scraped items successfully classified before index calculation.

---

## Phase 3: Econometric CPI Aggregation & Machine Learning Inflation Forecasting

*This phase executes the mathematical index aggregation and builds predictive models for forward-looking inflation forecasting.*

### 3.1 Econometric CPI Calculation (Two-Stage Aggregation)
1. **Stage 1 (Elementary Aggregates - Jevons Geometric Mean):**
   $$\bar{P}_{i, t} = \exp\left( \frac{1}{K} \sum_{k=1}^K \ln P_{i, k, t} \right)$$
   $$R_{i, t} = \left( \frac{\bar{P}_{i, t}}{\bar{P}_{i, 0}} \right) \times 100$$
2. **Stage 2 (Higher-Level Aggregates - Laspeyres Index):**
   $$I_{d, t} = \frac{1}{N_d} \sum_{i \in d} R_{i, t}$$
   $$\text{CPI}_t = \sum_{d=1}^{12} w_d \times I_{d, t} \quad \text{where } \sum_{d=1}^{12} w_d = 100.000\%$$
3. **Multilateral GEKS-Törnqvist Aggregation:** 13-period rolling window index preventing chain drift in e-commerce categories.

### 3.2 Feature Engineering for Inflation Forecasting
- **Time-Series Lagged Features:** 1-day, 7-day, 14-day, and 30-day price lags and rolling percentage changes.
- **Statistical Moments:** 7-day and 30-day rolling means, standard deviations, and price volatilities per division.
- **Macroeconomic Exogenous Regressors:** Daily MEF USD/KHR exchange rates, retail gasoline prices (MOC regular/diesel), and calendar seasonality flags (e.g., Khmer New Year, Pchum Ben festivals).

### 3.3 Machine Learning Forecasting Models
- **Baseline Models:** ARIMA / SARIMAX incorporating exogenous FX and fuel variables.
- **Decomposition & Seasonality:** **Prophet** for holiday effects and multi-scale weekly/monthly trends.
- **Non-Linear Tree Ensembles:** **XGBoost / LightGBM Regressors** for multi-step price momentum and non-linear feature interactions.
- **Deep Sequence Models:** **LSTM / GRU Neural Networks** for capturing long-term temporal dependencies in commodity price shocks.

### 3.4 Evaluation Metrics
- Models are evaluated using expanding rolling-window backtesting:
  $$\text{RMSE} = \sqrt{\frac{1}{n} \sum_{t=1}^n (\text{CPI}_t - \widehat{\text{CPI}}_t)^2}$$
  $$\text{MAPE} = \frac{100\%}{n} \sum_{t=1}^n \left| \frac{\text{CPI}_t - \widehat{\text{CPI}}_t}{\text{CPI}_t} \right|$$
  $$\text{MAE} = \frac{1}{n} \sum_{t=1}^n |\text{CPI}_t - \widehat{\text{CPI}}_t|$$

---

## Phase 4: Interactive Dashboard Development & Serving

*This phase delivers real-time analytical dashboards, model serving, and stakeholder interfaces.*

### 4.1 Metabase Executive BI Dashboard (`:3000`)
- **Headline Inflation Gauge:** Real-time National Headline CPI, Day-on-Day (DoD), and Year-on-Year (YoY) inflation rates.
- **12 COICOP Division Comparison:** Interactive charts comparing food inflation against core inflation.
- **Top Movers & Promo Impact:** Tables highlighting top rising and falling goods, and promotional discount depths.
- **Pipeline Data Quality Mart:** Ingestion quote volume, unclassified review queue count, and scraper success rates.

### 4.2 Streamlit ML & Human-in-the-Loop Application (`:8501`)
- **Interactive ML Forecasting Interface:** Allows analysts to select forecasting horizons (7-day, 30-day, 90-day), toggle models (Prophet vs. XGBoost vs. LSTM), and visualize predictive confidence intervals.
- **COICOP Labeling & Triage Tool:** Enables analysts to inspect unclassified/low-confidence items and confirm or correct assignments into `silver.coicop_override`.

### 4.3 Containerization & Production Deployment
- Orchestrated via **Docker Compose**:
  - `postgres` (PostgreSQL 16 database lakehouse)
  - `airflow-webserver` & `airflow-scheduler` (Pipeline orchestration)
  - `metabase` (Business intelligence dashboard)
  - `streamlit` (Human-in-the-loop and ML forecasting UI)
  - `ollama` (Local LLM fallback container)
