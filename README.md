# Cambodia Daily Consumer Price Index (CPI) Medallion Pipeline
*Automated Daily Web-Scraped Inflation Tracking across 12 UN COICOP Divisions (PostgreSQL 16 · dbt · Airflow · Metabase · Vector Embeddings · Gemini Pro/Flash)*

> **✅ Implementation Status:** The **data pipeline is 100% live and verified in production** end-to-end — scraping → Bronze ingestion → Silver cleaning / hybrid vector item matching / zero-mismatch 12-division AI-First classification → Gold star schema → Jevons/Laspeyres CPI calculation & ML nowcasting. All **1,000,000+ price observations** across 27 historical scrape dates (`2026-08-18` to `2026-09-14`) and **45,080 daily clean observations** are 100% classified into official **NIS Cambodia 4-digit COICOP Classes (`DD.G.C`)** with **0 code-division mismatches** and **0 unclassified items**, tracking **38,712 active elementary items** (Headline CPI: `100.3016`, Core CPI: `99.9296`, Nowcast MoM: `+0.714%`). Test suites: **dbt data & unit tests (`PASS=33 WARN=0 ERROR=0`)** and **Python tests passing (100% pass rate)**.

---

## 1. Architectural Blueprint & Tooling Matrix

| Layer | Tool | Why |
|:---|:---|:---|
| **Orchestration** | **Apache Airflow 2.9.3 & Astronomer Cosmos** | Schedules the daily `cpi_master_dag` (25 per-source scraper DAGs → `silver_dag` → `gold_cpi_dag` → `gold_dag`), dynamically parses dbt Core transformations into modular Airflow task nodes via Astronomer Cosmos, handles retries, and provides automated end-to-end Medallion execution. Sub-second DAG parsing achieved via decoupled `SCRAPER_SLUGS` in `scrapers/sources/slugs.py`. |
| **Storage & Warehouse** | **PostgreSQL 16 & pgvector** (`bronze`/`staging`/`silver`/`gold`/`ops` schemas) | Pure relational data warehouse hosting declarative monthly partitioned raw listings and clean observations, pgvector HNSW embeddings, item-matching state, cleaned facts, operational control tables, and the analytical star schema. |
| **Transformation** | **dbt-core & Astronomer Cosmos** (Silver & Gold) | Turns raw price records, entity-matching outputs, pack-size conversions, and COICOP classification into version-controlled, testable SQL models rendered as visual task groups in Airflow. |
| **Multi-Key API Pool** | **GeminiKeyPool** (`pipeline/key_pool.py`) | Thread-safe round-robin API key pool supporting 4+ free Gemini keys (6,000 req/day, 60 RPM) with automatic 429 failover. |
| **Semantic Item Matching** | **VectorItemMatcher** (`pipeline/vector_item_matcher.py`) | High-speed multilingual vector embeddings (local MiniLM / deterministic synonym vectorizer + cached `gemini-embedding-2`), deterministic spec guards (RAM/Storage, pack size, volume ≤ 10%), and batch AI review for borderline pairs. |
| **Direct COICOP Engine** | **GeminiCOICOPClassifier** (`pipeline/gemini_coicop_classifier.py`) | Direct, high-precision official NIS Cambodia 4-digit COICOP Class (`DD.G.C`) classification powered by Google Gemini Flash via `GeminiKeyPool` round-robin rotation, supporting bilingual Khmer & English context, domain guardrails, dual-matching query (new items + unclassified fallback), and persistent database caching. |
| **Scraper Observability** | **Metabase v0.49** | Real-time operational monitoring across 3 consolidated dashboards (Port 3001): Macro CPI Analytics, Operations & Scraper Health, and Silver Data Quality. |
| **Interactive Analytics** | **Microsoft Power BI** | Executive BI dashboards over the gold star schema: retailer and item-level price trends, promo analytics. |

---

## 2. Medallion Layer Overview

```
┌─────────────────┬───────────────────┬───────────────────────────┬──────────────────────────┬───────────────────────────────┐
│   25 SOURCES    │      BRONZE       │          SILVER           │           GOLD           │         SERVING & BI          │
│                 │  (Raw Ingestion)  │     (Clean & Resolve)     │  (Star Schema & Jevons)  │     (Observability & BI)      │
├─────────────────┼───────────────────┼───────────────────────────┼──────────────────────────┼───────────────────────────────┤
│ AEON 1 & AEON 3 │                   │                           │                          │                               │
│ Delishop Asia   │ bronze.raw_prices │ silver.canonical_items    │ gold.dim_items           │ METABASE (Port 3001):         │
│ Chip Mong Mart  ├──────────────────►│ silver.item_match_log     ├─────────────────────────►│ • 01: Macro CPI Analytics     │
│ Lucky Supermkt  │ staging.exchange_ │ silver.clean_store_prices │ gold.dim_stores          │   - Headline & Core Tickers   │
│ Ucare Pharmacy  │   rates           │   (Cleaned Append / Dedup)│ gold.fct_daily_prices    │   - Inflation Trendline       │
│ Ary & Samnang   │                   │ silver.classification_    │ gold.fct_elementary_     │   - 12-Division COICOP Table  │
│ Community Pharma│ staging.raw_      │   queue (AI triage)       │   indices (Jevons micro) │   - Top Basket Price Movers   │
│ Cellcard, Smart,│   scrapes         │ silver.int_prices_cleaned │ gold.fct_cpi_daily       │ • 02: Pipeline & Scraper Ops  │
│  & Metfone      │                   │ Vector Item Matcher       │   (12-Division Laspeyres)│   - Live Store Volume (Ranked)│
│ redBus &        │ (Typed Ingestion) │ 4-Key Gemini Pool +       │                          │   - Ingestion Matrix (14D)    │
│  BookMeBus      │ Atomic & Typed    │ 12-Division Reference     │ Jevons Micro-Index +     │   - Official MEF FX Rate Today│
│ KhmerMoto (Motos│ Rows in Postgres  │ Vector Cosine & Memo Cache│ 7-Day Imputation Engine  │   - Airflow Real-Time DAGs    │
│ EDC & PPWSA     │                   │                           │                          │ • 03: Silver Quality & Review │
│ Sokha & Hyatt   │                   │                           │                          │   - 12-Div Product Distr.     │
│ MOC Fuel & LPG  │                   │                           │                          │   - Log-Price Relative Dist.  │
│ MEF FX Daily    │                   │                           │                          │   - Outlier & Review Queues   │
│ ... (25 total)  │                   │                           │                          │                               │
└─────────────────┴───────────────────┴───────────────────────────┴──────────────────────────┴───────────────────────────────┘
```

### Bronze (Raw Ingestion & Staging)
- **Tables**: `bronze.raw_prices` (atomic typed listings with barcodes, brands, sizes, and prices), `staging.exchange_rates` (MEF USD/KHR official daily rate), `staging.raw_scrapes`.
- **Scraper Registry**: 25 production scrapers (`scrapers/sources/`) extracting native categories, automated fallbacks, and zero-product circuit breakers. Lightweight slug mapping decoupled in `scrapers/sources/slugs.py` for ~1s DAG parsing.
- **Ingestion Circuit Breaker (`pipeline/circuit_breaker.py`)**: Real-time quality gate checking volume drops (≥ 30% rolling median) and price velocity anomalies (± 50% deviation) with dynamic USD/KHR currency conversion using daily MEF exchange rates to prevent false alerts on USD-denominated retailers (Delishop, Cellcard, Hyatt, Sokha). Telemetry persisted to `ops.circuit_breaker_events`.

### Silver (Clean, Standardize & Resolve Observations)
- **Clean Store Observations**: `silver.clean_store_prices` — unified daily appended table containing cleaned, standardized prices across all stores with exchange rates applied (KHR via official MEF rate), Khmer numeral conversion (e.g. ៥០០ → 500), metric unit normalization (500g → 0.5kg, 1500ml → 1.5L), promo clamping, and unit price calculation ($P_{\text{unit}} = \text{Price in KHR} / \text{Normalized Metric}$).
- **4-Level Product Matching Waterfall**:
  1. *Level 1 (Universal Barcode)*: Matches identical items across different stores (e.g., AEON ↔ DeliShop) using global GTIN/EAN-13 barcodes.
  2. *Level 2 (Store ID + SKU Composite Key)*: Solves SKU collisions across retailers using a composite `(store_id, sku)` key with a "Learn once, cache forever" strategy to track returning items day-after-day.
  3. *Level 3 (Exact Clean Text Matching)*: Links identical products across retailers with different internal SKUs when barcodes are missing.
  4. *Level 4 (Vector Embedding & Deterministic Spec Guard)*: High-speed 768-dim semantic search (`gemini-embedding-2` via PostgreSQL `pgvector` HNSW Cosine Index Top 30) paired with a strict deterministic spec guard that rejects false physical merges (e.g., `1 can` $\neq$ `24-pack`, `128GB` $\neq$ `256GB`) with threshold $\ge 0.80$.
- **12-Division & 5-Digit NIS COICOP Engine**: `pipeline/gemini_coicop_classifier.py` executing a two-tier strategy: Tier 1 deterministic single-category store assignment (Smart/Cellcard → 08.3.0, BookMeBus → 07.3.2) + Tier 2 Gemini Flash batching (40 items/batch across 4 rotating API keys) with domain guardrails and permanent memoization in PostgreSQL (`silver.canonical_items`).
- **Operational Triage Queue**: `silver.classification_queue` captures unclassified or low-confidence items for automated review or human labeling.

### Gold (Kimball Star Schema & Jevons/Laspeyres CPI Engine)
- **Dimensional Modeling (Star Schema & Aggregate Marts)**:
  - `gold.dim_items`: Curated canonical product master dimension with COICOP attribution.
  - `gold.dim_items_history`: dbt SCD Type 2 snapshot tracking longitudinal changes in brand packaging and classification.
  - `gold.dim_stores`: Store & retailer master dimension.
  - `gold.fct_daily_prices`: Conformed daily price fact table at grain `(scrape_date, store_slug, item_id)` with KHR prices, unit prices, promo/outlier/fallback flags, and COICOP attribution.
  - `gold.fct_coicop_class_daily`: Intermediate 4-digit and 5-digit COICOP class-level aggregate mart for sub-division policy drilldown.
  - `gold.fct_cpi_monthly`: Monthly conformed 12-division and national headline/core CPI aggregate mart with Month-over-Month (MoM %) and Year-over-Year (YoY %) inflation rates.
  - `gold.dim_nis_official_cpi`: Official NIS Cambodia monthly CPI releases (Oct–Dec 2006 = 100) and full 12 COICOP division index benchmarks.
  - `gold.fct_cpi_nis_comparison`: Tracking error and benchmark evaluation mart comparing high-frequency pipeline CPI against official NIS monthly releases.
  - `gold.fct_cpi_nowcast`: Daily generated current-month inflation nowcasts with dynamic 95% confidence intervals, uncertainty decay ratios, and official NIS chain-linking.
- **Economic Index Calculation Engine (`pipeline/cpi_calculator.py`)**:
  - **Axiomatic Store-Balanced Jevons Elementary Aggregation (IMF/ILO CPI Manual 2020)**:
    - *Store-Level Jevons Index*: Unweighted geometric mean of micro-price relatives using numerical log-prices to eliminate arithmetic formula bias (Carli/Dutot drift):
      $$\ln I_{s,t}^{\text{Jevons}} = \frac{1}{n_s} \sum_{i=1}^{n_s} (\ln P_{i,s,t} - \ln P_{i,s,0})$$
    - *Store Balancing ("1 Store = 1 Vote")*: Elementary aggregates weight eligible stores equally within each category, preventing catalog-heavy retailers (e.g. 90 types of rice vs 10 types of rice) from overpowering smaller shops.
  - **New Products on Non-Base Dates (Baseline Entry Price Splicing)**: Products appearing after the initial base date establish their first observed quote as their personal baseline ($P_{i,s,0} = P_{\text{entry}}$, ratio 1.00), tracking subsequent price movements without creating fictitious historical shocks.
  - **ILO Class-Mean Imputation Engine**: Missing items ($\le 7$ days) are dynamically imputed using the geometric mean rate of change of observed items in the corresponding category. Items absent for $>7$ consecutive days are flagged as discontinued and cleanly dropped.
  - **Dual Chain-Linking Architecture**:
    - *Official NIS Benchmark Splicing*: Spliced to the official NIS 2006 base ($219.007$) using a conversion factor of $2.19007$ ($CPI_{\text{unified}} = CPI_{\text{web}} \times 2.19007$) for direct comparability with sovereign releases.
    - *Annual December Overlap Chain-Linking*: Resets annual base weights via the December monthly average, preventing artificial New Year index cliffs.
  - **Laspeyres 12-Division Weighting**: Synthesized using official Cambodia Socio-Economic Survey (CSES 2020) expenditure shares: Food & Beverages (44.775%), Housing & Utilities (17.062%), Transport (12.203%), and remaining 9 divisions (25.960%).
  - **Refined Core CPI**: Excludes volatile food (Division 01) and energy/utilities (Division 04) to monitor underlying structural macroeconomic price stability.
- **Two-Stage Hybrid Ridge Daily Inflation Nowcasting Engine (`ml/nowcaster.py`)**:
  - *Tier 1 (Realized Elapsed Days $1 \dots d$)*: 100% axiomatic scraped ground truth reality with zero econometric model error.
  - *Tier 2 (Forward Econometric Projection $d+1 \dots T$)*: `RidgeCV` $L_2$ regularization with Bayesian shrinkage priors modeling high-velocity basket drift with cross-sector fuel pass-through, USD/KHR exchange rate momentum, and Khmer holiday decay kernels.
  - *Dynamic Horizon Blending*: Time-weighted convergence formula ($Nowcast(d) = \frac{d}{T}\bar{I}_{\text{realized}} + \frac{T-d}{T}\hat{I}_{\text{projected}}$) with monotonically decaying uncertainty bounds ($U_d = \sqrt{(T-d)/T}$).
  - *Architecture Flowchart*: Generated and maintained via `scripts/generate_nowcasting_flowchart.py`.
- **Serving Views & Metabase Dashboards** (`sql/views.sql`):
  - `gold.v_nowcast_evaluation`: Real-time out-of-sample audit tracking daily nowcast error vs. official NIS monthly releases.
  - `gold.v_cpi_monthly_summary`: Monthly national headline and core CPI with MoM (%) and YoY (%) inflation indicators.
  - `gold.v_cpi_monthly_divisions`: Monthly 12-division COICOP performance matrix with official NIS expenditure weights.
  - `gold.v_cpi_inflation_summary`: Daily Headline & Core CPI DoD/MoM inflation metrics.
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
│   ├── _http.py           # Shared HTTP / rate-limiting client
│   └── sources/           # Modular SCRAPER_REGISTRY (25 sources: 24 retail/transit/utilities + MEF FX)
│       ├── _common.py     # Canonical normalization & HTTP request helpers
│       ├── aeon.py, arystore.py, cellcard.py, khmermoto.py, metfone.py, utilities.py, ...
│       └── __init__.py    # Registry mapping source_slug -> ScraperClass
├── pipeline/              # Core pipeline services
│   ├── cpi_calculator.py  # Jevons micro-index, 7-day imputation & Laspeyres CPI engine
│   ├── partition_manager.py # Proactive declarative table partition manager (ops.maintain_monthly_partitions)
│   ├── nis_cpi_importer.py # Official NIS monthly CPI ground-truth benchmark importer & seed synchronizer
│   ├── key_pool.py        # 4-Key Round-Robin Gemini API Pool & Failover Manager
│   ├── vector_item_matcher.py # 768-dim Vector Item Matcher & Spec Guards
│   ├── gemini_coicop_classifier.py # High-precision UN COICOP 2018 Gemini Flash Classifier
│   ├── item_matcher.py    # Silver item matching coordinator
│   ├── gemini_item_reviewer.py # AI & Rule-based auto-reviewer for borderline pairs
│   ├── text_clean.py      # Text normalization for item matching
│   ├── hedonic_regression.py # Log-linear hedonic quality adjustment
│   ├── bronze_ingestion.py # Bronze layer entry point
│   ├── bronze_scraper.py  # Raw scraper engine
│   ├── canonical.py       # Record normalization (Schema v1.0)
│   ├── config.py          # Database connection & environment config
│   └── migrations/        # PostgreSQL DDL migration scripts
├── ml/                    # High-frequency ML inflation nowcasting engine
│   ├── config.py          # Cambodian holiday calendars, uncertainty params & weights
│   └── nowcaster.py       # High-frequency daily inflation nowcasting & NIS chain-linking engine
├── scripts/               # Maintenance & operational CLI utilities
│   ├── run_cpi_backtest.py # Runs historical CPI backtest across all dates
│   ├── run_hierarchical_classification.py # High-speed batch COICOP classifier CLI
│   ├── deduplicate_canonical_items.py # Canonical item deduplication and alias consolidation
│   ├── automated_rule_suggester.py # Gemini-powered regex rule discovery from manual corrections
│   ├── generate_literature_review_excel.py # Generates 4-tab systematic literature review Excel
│   ├── backfill_silver_pipeline.py # Historical Silver layer backfill runner
│   ├── auto_review_items.py # CLI for running AI item match review queue
│   └── setup_metabase_dashboards.py # Provisions Metabase analytics dashboards
├── dbt/                   # dbt-core transformation project (dbt 1.8+ with native unit tests)
│   ├── dbt_project.yml
│   ├── profiles.yml
│   ├── models/            # Staging, Silver intermediate, and Gold analytical views
│   │   ├── staging/       # Source definitions & staging models
│   │   ├── silver/        # Silver intermediate models (int_coicop_classified, clean_store_prices, unit_tests)
│   │   └── gold/          # Gold dimensional models (dim_items, dim_stores, fct_daily_prices)
│   └── seeds/             # Category weights, COICOP overrides, NIS official benchmarks & utility tariffs
├── orchestration/         # Airflow orchestration stack & Astronomer Cosmos
│   ├── Dockerfile         # Unified container image (Airflow 2.9.3 + Cosmos + Playwright)
│   └── dags/              # DAG definitions
│       ├── cpi_master_dag.py   # Master orchestrator (Partition maintenance → 25 scrapers → silver → gold)
│       ├── cpi_maintenance_dag.py # Weekly database maintenance, partition pre-creation & ANALYZE
│       ├── scraper_dags.py     # Per-source scraper DAGs
│       ├── silver_dag.py       # Silver layer transformation (Astronomer Cosmos DbtTaskGroup)
│       ├── gold_dag.py         # Gold star schema + serving views (Astronomer Cosmos DbtTaskGroup)
│       ├── gold_cpi_dag.py     # Jevons/Laspeyres CPI calculation
│       ├── nis_cpi_dag.py      # Weekly official NIS monthly CPI release ingestion & benchmark tracking
│       └── alerts.py           # Task failure & SLA callbacks
├── sql/                   # Database DDL & serving views
│   ├── schema.sql         # Full relational schema (647 lines)
│   ├── views.sql          # Metabase serving views (143 lines)
│   └── migrations/        # Incremental migration scripts
├── tests/                 # Full pytest suite (435+ unit test cases across 20 test modules)
├── postgres-init/         # PostgreSQL initialization scripts
├── docker-compose.yml     # Multi-service stack (PostgreSQL, Airflow, Metabase)
├── Literature_Review_Matrix.xlsx # Root 4-tab literature review matrix & Cambodia CPI weights
└── .env                   # Environment configuration (secrets, API keys)
```

---

## 4. DAG Orchestration Flow

```
cpi_master_dag (Daily 08:00 ICT)
    │
    ├──► [25 Scraper DAGs] ──── bronze_complete
    │         │
    │         ▼
    │    verify_bronze_quality_gate (≥3 successful sources)
    │         │
    │         ▼
    │    silver_dag
    │         ├── task_item_matching (ItemMatcher)
    │         ├── task_item_auto_review (VectorItemMatcher + Gemini Flash)
    │         ├── task_dbt_seed (reference seeds & weights)
    │         ├── task_dbt_silver_run (clean_store_prices dedup & conformed facts)
    │         ├── task_gemini_coicop (HybridCOICOPClassifier)
    │         ├── task_hedonic_adjustment (Log-Linear Hedonic quality adjustment)
    │         └── task_dbt_silver_test (data quality tests)
    │         │
    │         ▼
    │    gold_cpi_dag
    │         ├── calculate_daily_cpi_indices (Two-tier Subclass & Division Laspeyres + Splice Factor)
    │         ├── calculate_monthly_cpi_indices (Windowed Laspeyres Monthly Mart - Single Writer)
    │         ├── nowcast_daily_inflation (ML-assisted daily inflation nowcast)
    │         └── annual_rebase_cpi (January continuous linking rebasing)
    │         │
    │         ▼
    │    gold_dag
    │         ├── dbt_gold_run (dim_items, dim_stores, fct_daily_prices, fct_coicop_class_daily)
    │         ├── dbt_gold_test (star schema tests)
    │         └── refresh_serving_views (Metabase serving views)
    │
    ▼
cpi_pipeline_success
```
