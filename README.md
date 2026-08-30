# Cambodia Daily Consumer Price Index (CPI) Medallion Pipeline
*Automated Daily Web-Scraped Inflation Tracking across 12 UN COICOP Divisions (PostgreSQL 16 · dbt · Airflow · Metabase · Vector Embeddings · Gemini Pro/Flash)*

![Cambodia CPI Architecture Diagram](docs/cpi_end_to_end_architecture_diagram.jpg)

> **⚠️ Implementation Status:** The **data pipeline is live** end-to-end — scraping → Bronze ingestion → Silver cleaning / hybrid vector item matching / 12-division AI classification → Gold star schema → Jevons/Laspeyres CPI calculation. Historical data from August 18 onwards is fully backfilled and unified. For details on the architecture and visual workflows, see [Architecture Diagrams](docs/ARCHITECTURE_DIAGRAMS.md).

---

## 1. Architectural Blueprint & Tooling Matrix

| Layer | Tool | Why |
|:---|:---|:---|
| **Orchestration** | **Apache Airflow 2.9.3** | Schedules the daily `cpi_master_dag` (20 per-source scraper DAGs → `silver_dag` → `gold_dag` → `gold_cpi_dag`), handles retries, and provides automated end-to-end Medallion execution. |
| **Storage & Warehouse** | **PostgreSQL 16** (`bronze`/`staging`/`silver`/`gold`/`ops` schemas) | Pure relational data warehouse hosting typed atomic raw listings, item-matching state, cleaned facts, operational control tables, and the analytical star schema. |
| **Transformation** | **dbt-core** (Silver & Gold) | Turns raw price records, entity-matching outputs, pack-size conversions, and COICOP classification into version-controlled, testable SQL models. |
| **Multi-Key API Pool** | **GeminiKeyPool** (`pipeline/key_pool.py`) | Thread-safe round-robin API key pool supporting 3+ free Gemini keys (4,500 req/day, 45 RPM) with automatic 429 failover. |
| **Semantic Item Matching** | **VectorItemMatcher** (`pipeline/vector_item_matcher.py`) | High-speed multilingual vector embeddings (local MiniLM / deterministic synonym vectorizer + cached `gemini-embedding-2`), deterministic spec guards (RAM/Storage, pack size, volume ≤ 10%), and batch AI review for borderline pairs. |
| **Hybrid COICOP Engine** | **HybridCOICOPClassifier** (`pipeline/hybrid_embeddings_classifier.py`) | 4-tier ladder: human authority overrides → 15 pure store domain locks (0.001ms) → 12-division reference vector cosine matching (resolving Community Pharma 06/12 split & AEON variety) → Gemini Pro AI fallback & Postgres memoization. |
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
│                 │                   │                           │                          │ • 03: Scraper Ingestion & QA  │
│                 │                   │                           │                          │   - Daily Ingestion Volume    │
│                 │                   │                           │                          │   - 14-Day Store Matrix       │
│                 │                   │                           │                          │   - Field Completeness (%)    │
│                 │                   │                           │                          │   - Outlier & Fallback Audit  │
│                 │                   │                           │                          │   - Classification Methods    │
└─────────────────┴───────────────────┴───────────────────────────┴──────────────────────────┴───────────────────────────────┘
```

### Bronze (Raw Ingestion & Staging)
- **Tables**: `bronze.raw_prices` (atomic typed listings with barcodes, brands, sizes, and prices), `staging.exchange_rates` (MEF USD/KHR official daily rate), `staging.raw_scrapes`.
- **Scraper Registry**: 20 production scrapers (`scrapers/sources.py`) extracting native categories, automated fallbacks, and zero-product circuit breakers.

### Silver (Clean, Standardize & Resolve Observations)
- **Clean Store Observations**: `silver.clean_store_prices` — unified daily appended table containing cleaned, standardized prices across all stores with exchange rates applied (KHR), unit normalization, promo clamping, and zero-price filtering.
- **Item Matching Service**: Python (`pipeline/item_matcher.py` & `pipeline/vector_item_matcher.py`) executing Barcode exact → SKU exact → Exact Text → Vectorized Matrix Cosine (S = M · v) + RapidFuzz with deterministic spec guards to reject storage/pack conflicts.
- **12-Division COICOP Engine**: `pipeline/hybrid_embeddings_classifier.py` executing 4-tier daily ladder: human overrides → 15 pure store locks → 12-division vector space matching → Gemini Pro AI fallback cached in `silver.dim_coicop_ai_cache`.
- **Operational Triage Queue**: `silver.classification_queue` captures unclassified or low-confidence items for automated review or human labeling.
- **COICOP Override System**: `silver.coicop_override` (seed-driven) + `silver.coicop_override_manual` (operator-driven) for persistent classification rules.

### Gold (Kimball Star Schema & Jevons/Laspeyres CPI Engine)
- **Dimensional Modeling (Star Schema & Aggregate Marts)**:
  - `gold.dim_items`: Curated canonical product master dimension with COICOP attribution.
  - `gold.dim_items_history`: dbt SCD Type 2 snapshot tracking longitudinal changes in brand packaging and classification.
  - `gold.dim_stores`: Store & retailer master dimension.
  - `gold.fct_daily_prices`: Conformed daily price fact table at grain `(scrape_date, store_slug, item_id)` with KHR prices, unit prices, promo/outlier/fallback flags, and COICOP attribution.
  - `gold.fct_coicop_class_daily`: Intermediate 4-digit COICOP class-level aggregate mart (e.g. `01.1.1` Bread & Cereals) for sub-division policy drilldown.
- **Economic Index Calculation Engine (`pipeline/cpi_calculator.py`)**:
  - **Jevons Micro-Index Compilation**: Unweighted geometric mean price ratios across active basket items:
    $$I_{j}^{t/0} = \exp\left(\frac{1}{n_t} \sum_{i=1}^{n_t} \ln P_{i,t} - \frac{1}{n_0} \sum_{i=1}^{n_0} \ln P_{i,0}\right) \times 100.0$$
  - **ILO Class-Mean Imputation Engine**: Missing items ($\le 7$ days) are dynamically imputed using the geometric mean rate of change of observed items in the corresponding COICOP division:
    $$P_{i,t} = P_{i,t-k} \times \left( \prod_{j \in D_i} \frac{P_{j,t}}{P_{j,t-1}} \right)^{\frac{1}{|D_i|}}$$
  - **Hedonic Quality Adjustment Bridge**: Directly bridges `silver.hedonic_adjusted_prices` to adjust for technology/electronic quality improvements (Division 08/09).
  - **Laspeyres 12-Division Weighting**: Official National Institute of Statistics (NIS) Cambodia expenditure shares compiled into Headline and Core CPI (`gold.fct_cpi_daily`).
  - **Refined Core CPI**: Excludes volatile food (Division 01) and energy/fuel in accordance with NIS and National Bank of Cambodia core inflation standards.
- **Serving Views & Metabase Dashboards** (`sql/views.sql`):
  - `gold.v_cpi_inflation_summary`: Headline & Core CPI DoD/MoM inflation metrics.
  - `gold.v_coicop_class_breakdown`: 4-digit COICOP class-level granular breakdown.
  - `gold.v_monitor_source_health_matrix`: 20-Source Scraper Live Availability Matrix.
  - `gold.v_monitor_price_alerts`: Daily price anomaly & extreme shift alerts (> 20% DoD).
  - `gold.v_monitor_fx_health`: Official MEF USD/KHR Exchange Rate Freshness Monitor.

---

## 3. Repository Layout

```
CPI PIPELINE/
├── scrapers/              # Python scraper modules (Bronze ingestion)
│   ├── base.py            # Abstract BaseScraper interface
│   └── sources.py         # SCRAPER_REGISTRY (20 sources: 19 retail + MEF FX)
├── pipeline/              # Core pipeline services
│   ├── cpi_calculator.py  # Jevons micro-index, 7-day imputation & Laspeyres CPI engine
│   ├── key_pool.py        # 3-Key Round-Robin Gemini API Pool & Failover Manager
│   ├── vector_item_matcher.py # 768-dim Vector Item Matcher & Spec Guards
│   ├── hybrid_embeddings_classifier.py # 12-Division Vector COICOP Classifier
│   ├── item_matcher.py    # Silver item matching coordinator
│   ├── gemini_item_reviewer.py # AI & Rule-based auto-reviewer for borderline pairs
│   ├── gemini_coicop_classifier.py # Gemini-based COICOP classifier
│   ├── text_clean.py      # Text normalization for item matching
│   ├── hedonic_regression.py # Log-linear hedonic quality adjustment
│   ├── bronze_ingestion.py # Bronze layer entry point
│   ├── bronze_scraper.py  # Raw scraper engine
│   ├── canonical.py       # Record normalization (Schema v1.0)
│   ├── config.py          # Database connection & environment config
│   └── migrations/        # PostgreSQL DDL migration scripts
├── scripts/               # Maintenance & operational CLI utilities
│   ├── run_cpi_backtest.py # Runs historical CPI backtest across all dates
│   ├── evaluate_accuracy_benchmark.py # End-to-end accuracy benchmark utility
│   ├── generate_literature_review_excel.py # Generates 4-tab systematic literature review Excel
│   ├── backfill_silver_pipeline.py # Historical Silver layer backfill runner
│   ├── bootstrap_vector_embeddings.py # Vector catalog pre-warming utility
│   ├── auto_review_items.py # CLI for running AI item match review queue
│   └── setup_metabase_dashboards.py # Provisions Metabase analytics dashboards
├── dbt/                   # dbt-core transformation project
│   ├── dbt_project.yml
│   ├── profiles.yml
│   ├── models/            # Staging, Silver intermediate, and Gold analytical views
│   │   ├── staging/       # Source definitions & staging models
│   │   ├── silver/        # Silver intermediate models (int_coicop_classified, clean_store_prices)
│   │   └── gold/          # Gold dimensional models (dim_items, dim_stores, fct_daily_prices)
│   └── seeds/             # Category weights, COICOP overrides & utility tariffs
├── orchestration/         # Airflow orchestration stack
│   ├── Dockerfile         # Unified container image (Airflow 2.9.3 + deps)
│   └── dags/              # DAG definitions
│       ├── cpi_master_dag.py   # Master orchestrator (20 scrapers → silver → gold)
│       ├── scraper_dags.py     # Per-source scraper DAGs
│       ├── silver_dag.py       # Silver layer transformation
│       ├── gold_dag.py         # Gold star schema + serving views
│       ├── gold_cpi_dag.py     # Jevons/Laspeyres CPI calculation
│       └── alerts.py           # Task failure & SLA callbacks
├── sql/                   # Database DDL & serving views
│   ├── schema.sql         # Full relational schema (647 lines)
│   ├── views.sql          # Metabase serving views (143 lines)
│   └── migrations/        # Incremental migration scripts
├── thesis/                # Academic Engineering Thesis LaTeX & Assets
│   ├── main.tex           # Master LaTeX compilation document
│   ├── Chapters/          # Ch 1-5 (Introduction, Literature Review, Methodology, Results)
│   ├── Cover_Pages/       # Multilingual covers (EN, KH, FR), acknowledgements, abstracts
│   └── Literature_Review_Matrix.xlsx # Comprehensive 4-tab systematic review spreadsheet
├── docs/                  # Centralized technical documentation & architectural guides
│   ├── ARCHITECTURE_DIAGRAMS.md # All 4 Medallion layer architectural diagrams
│   ├── diagrams/          # Individual .mmd Mermaid diagram source files
│   ├── COICOP_MAPPING.md  # 12-Division hierarchy & store domain classification
│   ├── LITERATURE_REVIEW.md # Academic foundation & comparative matrix
│   ├── PRODUCT_CLASSIFICATION_WORKFLOW.md # Pipeline lifecycle from scrape to gold
│   ├── SCRAPER_METHODOLOGY_GUIDE.md # 20 Source scraping specifications & tariffs
│   ├── SILVER_LAYOUT_DESIGN.md # Silver cleaned tables & operational data model
│   ├── GOLD_LAYER_CPI_METHODOLOGY_GUIDE.md # CPI calculation methodology
│   ├── GOLD_LAYER_IMPLEMENTATION_PLAN.md # Gold layer implementation roadmap
│   └── rebasing_policy.md # Annual CPI rebasing methodology
├── tests/                 # Full pytest suite (140 unit test cases)
├── postgres-init/         # PostgreSQL initialization scripts
├── docker-compose.yml     # Multi-service stack (PostgreSQL, Airflow, Metabase)
├── Literature_Review_Matrix.xlsx # Root 4-tab literature review matrix & Cambodia CPI weights
└── .env                   # Environment configuration (secrets, API keys)
```

---

## 4. DAG Orchestration Flow

```
cpi_master_dag (Daily 02:00 ICT)
    │
    ├──► [20 Scraper DAGs] ──── bronze_complete
    │         │
    │         ▼
    │    verify_bronze_quality_gate (≥3 successful sources)
    │         │
    │         ▼
    │    silver_dag
    │         ├── silver_item_matching_service (ItemMatcher)
    │         ├── gemini_item_auto_review (VectorItemMatcher + Gemini Flash)
    │         ├── dbt_seed (reference data)
    │         ├── gemini_coicop_classification (HybridCOICOPClassifier)
    │         ├── hedonic_quality_adjustment (Log-Linear Hedonic)
    │         ├── dbt_silver_run (incremental models)
    │         └── dbt_silver_test (data quality)
    │         │
    │         ▼
    │    gold_dag
    │         ├── dbt_gold_run (dim_items, dim_stores, fct_daily_prices)
    │         ├── dbt_gold_test (star schema tests)
    │         └── refresh_serving_views (Metabase views)
    │         │
    │         ▼
    │    gold_cpi_dag
    │         ├── calculate_daily_cpi_indices (Jevons + Laspeyres)
    │         └── annual_rebase_cpi (January rebasing)
    │
    ▼
cpi_pipeline_success
```

---

## 5. Key Code Changes & Fixes (Recent)

### Local-First Vector Matching & Caching (2026-08-28)
- **Files**: `pipeline/vector_item_matcher.py`, `pipeline/hybrid_embeddings_classifier.py`, `dbt/models/silver/schema.yml`
- **Issue**: Gemini API free-tier embedding rate limits (1000 req/day, 15 RPM) caused 429 quota exhaustion and 30-50s sleep delays during Silver item matching and COICOP classification.
- **Fix**:
  - Enabled fast local embeddings by default (`USE_LOCAL_FALLBACK_FIRST=true`) via `SentenceTransformer` / deterministic synonym vectorization, dropping matching latency from 25+ minutes to < 1-2 seconds.
  - Added in-memory embedding cache (`_embed_cache`) in `VectorItemMatcher` and `HybridCOICOPClassifier` to eliminate redundant vector recalculations.
  - Replaced row-by-row LLM arbitration with local score thresholding, keeping Gemini Flash LLM for large batch review jobs.
  - Fixed `ops.coicop_override_manual` database view binding and unit test numeric precision typing in `dbt`.

### MocGasolineScraper Resilience (2026-08-27)
- **File**: `scrapers/sources.py`
- **Issue**: `datetime.date` type incompatibility when `bronze_ingestion.py` passes raw date objects to scrapers.
- **Fix**: Added pendulum date conversion with 3x retry with exponential backoff, switched from `requests.post` to `_cffi_post`, added `MOC_FUEL_BASELINE` fallback catalog (5000/4050/3950 KHR) for API failures.

### Gemini Model Updates (2026-08-27)
- **Files**: `pipeline/hybrid_embeddings_classifier.py`, `pipeline/vector_item_matcher.py`
- **Changes**: Updated model identifiers:
  - `text-embedding-004` → `gemini-embedding-2`
  - `gemini-2.5-flash` → `gemini-3.5-flash`
- **Environment Variables**: `GEMINI_EMBEDDING_MODEL`, `GEMINI_PRO_MODEL`

### DB Constraint Fix (2026-08-27)
- **File**: `pipeline/migrations/004_silver_item_matching.sql`
- **Issue**: `item_match_log.match_method` constraint was missing `exact_text` value.
- **Fix**: Added `exact_text` to the CHECK constraint: `('barcode_exact', 'sku_exact', 'fuzzy_text', 'new_item', 'exact_text')`

### Ops Schema Pass-Through Views (2026-08-27)
- **Database**: `cpi_db` → `ops` schema
- **Issue**: dbt models reference `ops.*` schema but tables exist in `silver.*`.
- **Fix**: Created pass-through views in `ops` schema:
  - `ops.dim_coicop_ai_cache` → `silver.dim_coicop_ai_cache`
  - `ops.coicop_category_map` → `silver.coicop_category_map`
  - `ops.classification_queue` → `silver.classification_queue`
  - `ops.coicop_override_manual` (real table, not view)

### Gold DAG View Refresh Fix (2026-08-27)
- **File**: `orchestration/dags/gold_dag.py`
- **Issue**: PostgreSQL `CREATE OR REPLACE VIEW` fails when column names change between versions.
- **Fix**: Added automatic DROP of all `gold.*` views before recreating them in `_refresh_serving_views()`.

### COICOP Method Accepted Values (2026-08-27)
- **File**: `dbt/models/silver/schema.yml`
- **Issue**: `coicop_method` test was missing `review` as an accepted value.
- **Fix**: Added `"review"` to the accepted values list for `int_coicop_classified.coicop_method`.

---

## 6. Operational Commands & Utilities

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

### 6. Check DAG Run Status
```bash
docker exec airflow-scheduler airflow tasks states-for-dag-run <dag_id> <run_id>
```

### 7. Clear Failed Tasks for Retry
```bash
docker exec airflow-scheduler airflow tasks clear <dag_id> -t <task_id> -f -y
```

### 8. Access Metabase Dashboards
```bash
open http://localhost:3000
```

### 9. Access Airflow Web UI
```bash
open http://localhost:8085
```

---

## 7. Environment Variables

### Required Secrets (`.env`)
```bash
# Airflow
AIRFLOW_ADMIN_USER=admin
AIRFLOW_ADMIN_PASSWORD=<strong-password>
AIRFLOW__CORE__FERNET_KEY=<generated-key>
AIRFLOW__WEBSERVER__SECRET_KEY=<generated-key>

# Database
CPI_DB_PASSWORD=<db-password>
DB_PASS=<db-password>
POSTGRES_PASSWORD=<postgres-password>
METABASE_PASSWORD=<metabase-password>

# Gemini AI
GEMINI_API_KEY=<api-key>
GEMINI_API_KEYS=<key1>,<key2>,<key3>  # Optional multi-key pool
```

### Optional Configuration (`.env`)
```bash
# Pipeline
BASE_PERIOD=2026-08
DEFAULT_USD_KHR_RATE=4044
MEF_FX_API_URL=https://data.mef.gov.kh/api/v1/realtime-api/exchange-rate

# Gemini Models (defaults shown)
GEMINI_EMBEDDING_MODEL=models/gemini-embedding-2
GEMINI_PRO_MODEL=gemini-3.5-flash
GEMINI_MAX_ITEMS_PER_RUN=1000
USE_LOCAL_FALLBACK_FIRST=true

# Scraper Limits
AEON_MAX_PAGES=0
MIN_SUCCESSFUL_SCRAPERS=3
```

---

## 8. Database Schemas

| Schema | Purpose | Key Tables |
|:---|:---|:---|
| `bronze` | Raw store listings | `raw_prices`, `scrape_errors` |
| `staging` | Ingestion staging | `raw_scrapes`, `exchange_rates`, `bronze_ingestion_stats` |
| `silver` | Clean observations & dims | `canonical_items`, `clean_store_prices`, `item_match_log`, `needs_review`, `dim_coicop_ai_cache`, `coicop_override`, `coicop_override_manual`, `coicop_category_map`, `classification_queue` |
| `gold` | Analytical star schema | `dim_items`, `dim_stores`, `fct_daily_prices`, `fct_elementary_indices`, `fct_cpi_daily` |
| `ops` | Control-flow tables | Pass-through views over `silver.*` + `coicop_override_manual` table |

---

## 9. Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_item_matcher.py -v

# Run with coverage
python -m pytest tests/ --cov=pipeline --cov-report=term-missing
```

**Test Coverage**: 140 unit test cases covering:
- Item matching (barcode, SKU, fuzzy, vector)
- COICOP classification (4-tier ladder)
- CPI calculation (Jevons, Laspeyres, imputation)
- Text normalization & spec guards
- Bronze ingestion & canonicalization

---

## 10. License

Internal project — Cambodia CPI Pipeline Team.
