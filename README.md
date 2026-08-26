# Cambodia Daily Consumer Price Index (CPI) Medallion Pipeline
*Automated Daily Web-Scraped Inflation Tracking across 12 UN COICOP Divisions (PostgreSQL 16 · dbt · Airflow · Metabase · Vector Embeddings · Gemini Pro/Flash)*

![Cambodia CPI Architecture Diagram](docs/cpi_end_to_end_architecture_diagram.jpg)

> **⚠️ Implementation Status:** The **data pipeline is live** end-to-end — scraping → Bronze ingestion → Silver cleaning / hybrid vector item matching / 12-division AI classification → Gold star schema. Historical data from August 18 onwards is fully backfilled and unified. For details on the architecture and visual workflows, see [Architecture Diagrams](docs/ARCHITECTURE_DIAGRAMS.md).

---

## 1. Architectural Blueprint & Tooling Matrix

| Layer | Tool | Why |
|:---|:---|:---|
| **Orchestration** | **Apache Airflow 2.9.3** | Schedules the daily `cpi_master_dag` (20 per-source scraper DAGs → `silver_dag` → `gold_dag`), handles retries, and provides automated end-to-end Medallion execution. |
| **Storage & Warehouse** | **PostgreSQL 16** (`bronze`/`staging`/`silver`/`gold` schemas) | Pure relational data warehouse hosting typed atomic raw listings, item-matching state, cleaned facts, and the analytical star schema. |
| **Transformation** | **dbt-core** (Silver & Gold) | Turns raw price records, entity-matching outputs, pack-size conversions, and COICOP classification into version-controlled, testable SQL models. |
| **Multi-Key API Pool** | **GeminiKeyPool** (`pipeline/key_pool.py`) | Thread-safe round-robin API key pool supporting 3+ free Gemini keys ($4,500$ req/day, $45$ RPM) with automatic 429 failover. |
| **Semantic Item Matching** | **VectorItemMatcher** (`pipeline/vector_item_matcher.py`) | 768-dim multilingual embeddings (`text-embedding-004`), deterministic spec guards (RAM/Storage, pack size, volume $\le 10\%$), and `gemini-2.5-pro` LLM arbitration for borderline pairs. |
| **Hybrid COICOP Engine** | **HybridCOICOPClassifier** (`pipeline/hybrid_embeddings_classifier.py`) | 4-tier ladder: human authority overrides $\to$ 15 pure store domain locks ($0.001\text{ms}$) $\to$ 12-division reference vector cosine matching (resolving Community Pharma 06/12 split & AEON variety) $\to$ Gemini Pro LLM fallback & Postgres memoization. |
| **Scraper Observability** | **Metabase v0.49** | Real-time operational monitoring: 20-Source Live Health Matrix, daily ingestion volume trends, and price anomaly alerts. |
| **Interactive Analytics** | **Microsoft Power BI** | Executive BI dashboards over the gold star schema: retailer and item-level price trends, promo analytics. |

---

## 2. Medallion Layer Overview

```
┌─────────────────┬───────────────────┬───────────────────────────┬──────────────────────────┬───────────────────────────────┐
│   20 SOURCES    │      BRONZE       │          SILVER           │           GOLD           │         SERVING & BI          │
│                 │  (Raw Ingestion)  │     (Clean & Resolve)     │  (Star Schema & Jevons)  │     (Observability & BI)      │
├─────────────────┼───────────────────┼───────────────────────────┼──────────────────────────┼───────────────────────────────┤
│ AEON 1 & AEON 3 │                   │                           │                          │                               │
│ Delishop Asia   │ bronze.raw_prices │ silver.canonical_items    │ gold.dim_items           │ METABASE (Port 3000):         │
│ Ary & Samnang   ├──────────────────►│ silver.item_match_log     ├─────────────────────────►│ • 01: Daily CPI Dashboard     │
│ Community Pharma│ staging.exchange_ │ silver.clean_store_prices │ gold.dim_stores          │   - Headline & Core Tickers   │
│ Cellcard & Smart│   rates           │   (Cleaned Append / Dedup)│ gold.fct_daily_prices    │   - Inflation Trendline       │
│ redBus &        │                   │ silver.classification_    │ gold.fct_elementary_     │   - 12-Division COICOP Table  │
│  BookMeBus      │ staging.raw_      │   queue (AI triage)       │   indices (Jevons micro) │   - Top Basket Price Movers   │
│ Sokha & Hyatt   │   scrapes         │ staging.int_prices_cleaned│ gold.fct_cpi_daily       │ • 02: Pipeline Monitoring     │
│ MOC Fuel (Gas)  │                   │ Vector Item Matcher       │   (12-Division Laspeyres)│   - 20 Scraper Status & Vol   │
│ MEF FX Daily    │ (Typed Ingestion) │ 3-Key Gemini Pool +       │                          │   - Airflow Real-Time DAGs    │
│ ... (20 total)  │ Atomic & Typed    │ 12-Division Reference     │ Jevons Micro-Index +     │   - MEF FX Exchange Rate      │
│                 │ Rows in Postgres  │ Vector Cosine & Memo Cache│ 7-Day Imputation Engine  │   - Retail Fuel Prices Feed   │
└─────────────────┴───────────────────┴───────────────────────────┴──────────────────────────┴───────────────────────────────┘
```

### Bronze (Raw Ingestion & Staging)
- **Tables**: `bronze.raw_prices` (atomic typed listings with barcodes, brands, sizes, and prices), `staging.exchange_rates` (MEF USD/KHR official daily rate), `staging.raw_scrapes`.
- **Scraper Registry**: 20 production scrapers (`scrapers/sources.py`) extracting native categories, automated fallbacks, and zero-product circuit breakers.

### Silver (Clean, Standardize & Resolve Observations)
- **Clean Store Observations**: `silver.clean_store_prices` — unified daily appended table containing cleaned, standardized prices across all stores with exchange rates applied (KHR), unit normalization, promo clamping, and zero-price filtering.
- **Item Matching Service**: Python (`pipeline/item_matcher.py` & `pipeline/vector_item_matcher.py`) executing Barcode exact → SKU exact → Vectorized Matrix Cosine ($\mathbf{S} = \mathbf{M} \cdot \mathbf{v}$) + RapidFuzz with deterministic spec guards to reject storage/pack conflicts.
- **12-Division COICOP Engine**: `pipeline/hybrid_embeddings_classifier.py` executing 4-tier daily ladder: human overrides $\to$ 15 pure store locks $\to$ 12-division vector space matching $\to$ Gemini Pro LLM fallback cached in `silver.dim_coicop_ai_cache`.
- **Operational Triage Queue**: `silver.classification_queue` captures unclassified or low-confidence items for automated review or human labeling.

### Gold (Kimball Star Schema & Jevons/Laspeyres CPI Engine)
- **Dimensional Modeling (Star Schema)**:
  - `gold.dim_items`: Curated canonical product master dimension with COICOP attribution.
  - `gold.dim_stores`: Store & retailer master dimension.
  - `gold.fct_daily_prices`: Conformed daily price fact table at grain `(scrape_date, store_slug, item_id)` with KHR prices, unit prices, promo/outlier/fallback flags, and COICOP attribution.
- **Economic Index Calculation Engine (`pipeline/cpi_calculator.py`)**:
  - **Jevons Micro-Index Compilation**: Unweighted geometric mean price ratios across active basket items:
    $$I_{j}^{t/0} = \exp\left(\frac{1}{n_t} \sum_{i=1}^{n_t} \ln P_{i,t} - \frac{1}{n_0} \sum_{i=1}^{n_0} \ln P_{i,0}\right) \times 100.0$$
  - **7-Day Missing Price Imputation**: Carries forward the last valid observed price for temporary retail stockouts $\le 7$ days.
  - **Hedonic Quality Adjustment Bridge**: Directly bridges `silver.hedonic_adjusted_prices` to adjust for technology/electronic quality improvements (Division 08/09).
  - **Laspeyres 12-Division Weighting**: Official National Institute of Statistics (NIS) Cambodia expenditure shares compiled into Headline and Core CPI (`gold.fct_cpi_daily`).
  - **Refined Core CPI**: Excludes volatile food (Division 01) and energy/fuel in accordance with NIS and National Bank of Cambodia core inflation standards.

---

## 3. Repository Layout

```
CPI PIPELINE/
├── scrapers/              # Python scraper modules (Bronze ingestion)
│   ├── base.py            # Abstract BaseScraper interface
│   └── sources.py         # SCRAPER_REGISTRY (19 retail sources + MEF FX)
├── pipeline/              # Core pipeline services
│   ├── cpi_calculator.py  # Jevons micro-index, 7-day imputation & Laspeyres CPI engine
│   ├── key_pool.py        # 3-Key Round-Robin Gemini API Pool & Failover Manager
│   ├── vector_item_matcher.py # 768-dim Vector Item Matcher & Spec Guards
│   ├── hybrid_embeddings_classifier.py # 12-Division Vector COICOP Classifier
│   ├── item_matcher.py    # Silver item matching coordinator
│   ├── gemini_item_reviewer.py # AI & Rule-based auto-reviewer for borderline pairs
│   ├── text_clean.py      # Text normalization for item matching
│   └── hedonic_regression.py # Log-linear hedonic quality adjustment
├── scripts/               # Maintenance & operational CLI utilities
│   ├── run_cpi_backtest.py # Runs historical CPI backtest across all dates
│   ├── evaluate_accuracy_benchmark.py # End-to-end accuracy benchmark utility
│   ├── backfill_silver_pipeline.py # Historical Silver layer backfill runner
│   ├── bootstrap_vector_embeddings.py # Vector catalog pre-warming utility
│   ├── auto_review_items.py # CLI for running AI item match review queue
│   └── setup_metabase_dashboards.py # Provisions Metabase analytics dashboards
├── dbt/                   # dbt-core transformation project
│   ├── dbt_project.yml
│   ├── profiles.yml
│   ├── models/            # Staging, Silver intermediate, and Gold analytical views
│   └── seeds/             # Category weights, COICOP overrides & utility tariffs
├── orchestration/         # Airflow orchestration stack
│   ├── Dockerfile         # Unified container image (Airflow 2.9.3 + deps)
│   └── dags/              # cpi_master_dag, scraper_dags, silver_dag, gold_dag, gold_cpi_dag
├── docs/                  # Centralized technical documentation & architectural guides
│   ├── ARCHITECTURE_DIAGRAMS.md # All 4 Medallion layer architectural diagrams
│   ├── diagrams/          # Individual .mmd Mermaid diagram source files
│   ├── COICOP_MAPPING.md  # 12-Division hierarchy & store domain classification
│   ├── LITERATURE_REVIEW.md # Academic foundation & comparative matrix
│   ├── PRODUCT_CLASSIFICATION_WORKFLOW.md # Pipeline lifecycle from scrape to gold
│   ├── SCRAPER_METHODOLOGY_GUIDE.md # 20 Source scraping specifications & tariffs
│   └── SILVER_LAYOUT_DESIGN.md # Silver cleaned tables & operational data model
├── sql/                   # Database DDL: schema.sql, views.sql
├── tests/                 # Full pytest suite (140 unit test cases)
└── docker-compose.yml     # Multi-service stack (PostgreSQL, Airflow, Metabase)
```

---

## 4. Operational Commands & Utilities

### 1. Run Historical Daily CPI Backtest (Aug 18 Onwards)
```bash
python scripts/run_cpi_backtest.py
```
*Computes Jevons micro-indices, applies 7-day imputation, and generates daily Headline and Core CPI facts in `gold.fct_cpi_daily`.*

### 2. Run Comprehensive Accuracy Benchmark
```bash
python scripts/evaluate_accuracy_benchmark.py
```
*Evaluates product matching, spec guards, and 12-division COICOP semantic classification with full scorecards.*

### 3. Historical Data Backfill (August 18 Onwards)
```bash
python scripts/backfill_silver_pipeline.py --start-date 2026-08-18
```

### 4. Run Full Automated Test Suite
```bash
python -m pytest tests/ -v
```

### 5. Trigger Airflow Master DAG (Daily Fan-Out & Gold CPI)
```bash
docker compose exec airflow-scheduler airflow dags trigger cpi_master_dag
```
