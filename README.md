# Cambodia Daily Consumer Price Index (CPI) Medallion Pipeline
*Automated Daily Web-Scraped Inflation Tracking across 12 UN COICOP Divisions (PostgreSQL 16 · dbt · Airflow · Metabase)*

![Cambodia CPI Architecture Diagram](docs/cpi_simple_architecture.jpg)

---

## 1. Architectural Blueprint & Tooling Matrix

| Layer | Tool | Why |
|:---|:---|:---|
| **Orchestration** | **Apache Airflow 2.9.3** | Schedules the daily `cpi_master_dag` (20 per-source scraper DAGs → `silver_dag` → `gold_dag`), handles retries, and provides automated end-to-end Medallion execution. |
| **Storage & Warehouse** | **PostgreSQL 16** (`bronze`/`staging`/`silver`/`gold` schemas) | Pure relational data warehouse hosting typed atomic raw listings, item-matching state, cleaned facts, and analytical CPI marts. |
| **Transformation** | **dbt-core** (Silver & Gold) | Turns raw price records, entity-matching outputs, Jevons calculations, pack-size conversions, and COICOP weighted roll-ups into version-controlled, testable SQL models. |
| **Item Matching (Silver)** | **Python Service** (`ItemMatcher` with `RapidFuzz`) | Exact barcode & SKU matching with fallback token-sort fuzzy matching in Python, landing structured mappings (`silver.canonical_items`, `silver.item_match_log`). |
| **Hybrid Classification** | **Rule Engine (dbt SQL)** + **Gemini AI** (`gemini-3.1-flash-lite` / `gemini-2.5-flash`) | Daily-scoped 9-tier ladder: store purity, data-driven keyword rules (`coicop_keywords.csv`), category maps, and high-throughput Gemini cache (`silver.dim_coicop_ai_cache`, functional expression index `idx_coicop_ai_norm`, batched at 50 items/call via `scripts/warm_coicop_ai_cache.py`). |
| **Index Math (Silver & Gold)** | **dbt SQL** + **Python** (`GEKSCalculator`, `FisherCalculator`) | Elementary Jevons prices (`silver.fct_jevons_daily`), Laspeyres category & headline aggregations (`gold.cpi_category_daily`, `gold.cpi_headline_daily`), 12 dedicated Gold COICOP division tables, rolling 13-period multilateral GEKS-Törnqvist indices (`gold.cpi_geks_multilateral`), and Superlative Fisher Ideal indices (`gold.cpi_fisher_superlative`). |
| **Scraper Observability** | **Metabase v0.49** | Real-time operational monitoring: 20-Source Live Health Matrix, daily ingestion volume trends, and price anomaly alerts. |
| **Interactive Analytics** | **Microsoft Power BI** | Executive BI dashboards: National headline CPI, 12 COICOP division time-series, month-on-month inflation, substitution bias, and item-level price trends. |

---

## 2. Medallion Layer Overview

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                         PURE STRUCTURED MEDALLION ARCHITECTURE                                         │
├─────────────────┬───────────────────┬───────────────────────────┬──────────────────────┬───────────────────────────────┤
│   20 SOURCES    │      BRONZE       │          SILVER           │         GOLD         │         SERVING & BI          │
│                 │  (Raw Ingestion)  │     (Clean & Resolve)     │    (CPI Indices)     │     (Observability & BI)      │
├─────────────────┼───────────────────┼───────────────────────────┼──────────────────────┼───────────────────────────────┤
│ AEON 1 & AEON 3 │                   │                           │                      │                               │
│ Delishop Asia   │ bronze.raw_prices │ silver.canonical_items    │ gold.base_prices     │ METABASE (Port 3000):         │
│ Ary & Samnang   ├──────────────────►│ silver.item_match_log     ├─────────────────────►│ • Executive Macro Observatory │
│ Community Pharma│ staging.exchange_ │ silver.dim_items          │ gold.fct_daily_price │ • 12 COICOP Division Trends   │
│ Cellcard & Smart│   rates           │ silver.fct_daily_prices   │   _stats (Jevons)    │ • Retailer Price & Promo BI   │
│ redBus &        │                   │ silver.fct_jevons_daily   │ gold.cpi_category    │ • 20-Source Health & Ops Grid │
│  BookMeBus      │ staging.raw_      │   (Elementary Relatives)  │   _daily (COICOP)    │ • Price Anomaly Triage Feed   │
│ Sokha & Hyatt   │   scrapes         │ silver.fct_laspeyres      │ gold.cpi_headline    │ • Headline CPI Time-Series    │
│ MOC Fuel (Gas)  │ (Typed Ingestion) │   _daily (12 Divisions)   │   _daily (Laspeyres) │ • 12 COICOP Division Charts   │
│ MEF FX Daily    │                   │ silver.fct_laspeyres      │ gold.cpi_div01_food  │ • MoM / DoD Inflation Rate    │
│ ... (20 total)  │ Atomic & Typed    │   _headline_daily         │   ... to div12_misc  │ • Spliced Multilateral GEKS   │
│                 │ Rows in Postgres  │ Python RapidFuzz matching │ gold.cpi_geks        │ • Superlative Fisher Index    │
│                 │                   │ Hybrid Gemini AI Fallback │   _multilateral      │ • Consumer Substitution Bias  │
│                 │                   │                           │ gold.cpi_fisher      │                               │
│                 │                   │                           │   _superlative       │                               │
└─────────────────┴───────────────────┴───────────────────────────┴──────────────────────┴───────────────────────────────┘
```

### Bronze (Raw Ingestion & Staging)
- **Tables**: `bronze.raw_prices` (atomic typed listings with barcodes, brands, sizes, and prices), `staging.exchange_rates` (MEF USD/KHR official daily rate), `staging.raw_scrapes`.
- **Scraper Registry**: 20 production scrapers (`scrapers/sources.py`) extracting native categories, automated fallbacks, and zero-product quality gates.

### Silver (Clean, Resolve & Elementary Aggregation)
- **Item Matching Service**: Python (`pipeline/item_matcher.py`) executing Barcode exact → SKU exact → RapidFuzz token sort ratio writing to `silver.canonical_items` and `silver.item_match_log`.
- **Hybrid COICOP Engine**: daily-scoped 9-tier ladder (`int_coicop_classified.sql`): overrides -> store purity -> gated AI cache -> traps -> two-tier keyword rules (`coicop_keywords.csv`) -> category map -> defaults.
- **Elementary Jevons Geometric Mean**:
  - `silver.fct_jevons_daily`: Computes store-unweighted elementary geometric mean prices ($P_{\text{Jevons}}$) per canonical item, standardized unit prices, quote counts, and store density metrics.

### Gold (Serving, 12 Division Tables & Multilateral Aggregation)
- **12 Dedicated Division Tables**: `gold.cpi_div01_food` through `gold.cpi_div12_misc` exposing granular product price trends, base indices, and metrics per COICOP division.
- **Headline CPI & Elementary Stats**: `gold.base_prices` (August 2026 reference prices), `gold.fct_daily_price_stats` (Class-Mean Imputed geometric mean prices, ILO standard), `gold.cpi_category_daily`, and `gold.cpi_headline_daily`.
- **Advanced Econometrics**: Multilateral GEKS-Törnqvist service (`pipeline/geks_calculator.py`) with Movement Splicing, Superlative Fisher Ideal Index (`pipeline/fisher_calculator.py`) measuring consumer substitution bias, and log-linear Hedonic Quality Adjustment (`pipeline/hedonic_regression.py`) for Division 09 electronics.

---

## 3. Repository Layout

```
CPI PIPELINE/
├── scrapers/              # Python scraper modules (Bronze ingestion)
│   ├── base.py            # Abstract BaseScraper interface
│   └── sources.py         # SCRAPER_REGISTRY (19 retail sources + MEF FX)
├── pipeline/              # Core pipeline services
│   ├── bronze_ingestion.py# Bronze ingestion entrypoint (fetch → normalize → PostgreSQL)
│   ├── bronze_scraper.py  # BronzeScraper batch writer & FX store
│   ├── canonical.py       # Canonical Bronze Schema v1.0 normalize/validate
│   ├── item_matcher.py    # Silver item matching service (RapidFuzz)
│   ├── text_clean.py      # Text normalization for item matching
│   ├── gemini_coicop_classifier.py # Gemini AI batch classifier & cache
│   ├── geks_calculator.py # Gold multilateral GEKS-Törnqvist service (Movement Splice)
│   ├── fisher_calculator.py # Superlative Fisher Ideal index & bias
│   └── hedonic_regression.py # Log-linear hedonic quality adjustment
├── scripts/               # Maintenance & operational CLI utilities
│   ├── warm_coicop_ai_cache.py # Pre-warms Gemini AI classification cache
│   ├── recalculate_gold.py # Re-runs Gold stored procedures over date ranges
│   ├── setup_metabase_dashboards.py # Provisions Metabase analytics dashboards
│   └── clear_db_locks.py  # Clears stale PostgreSQL locks
├── dbt/                   # dbt-core transformation project
│   ├── dbt_project.yml
│   ├── profiles.yml
│   ├── models/            # Staging, Silver intermediate, and Gold analytical views
│   ├── seeds/             # Category weights, COICOP overrides & utility tariffs
│   └── tests/             # Singular price sanity, traps & idempotency tests
├── orchestration/         # Airflow orchestration stack
│   ├── Dockerfile         # Unified container image (Airflow 2.9.3 + deps)
│   └── dags/              # cpi_master_dag, scraper_dags, silver_dag, gold_dag
├── docs/                  # Centralized technical documentation & architectural guides
│   ├── CPI_END_TO_END_CALCULATION_GUIDE.md # Comprehensive math & data walkthrough
│   ├── ARCHITECTURE.md    # System architecture & Medallion specifications
│   ├── CPI_METHODOLOGY.md # 6-Layer CPI econometric methodology reference
│   ├── METABASE_DASHBOARD_BLUEPRINT.md # Metabase cards & dashboard specs
│   └── POWER_BI_SETUP_GUIDE.md # Power BI data model & DAX guide
├── sql/                   # Database DDL: schema.sql, views.sql, gold_procedures.sql
├── postgres-init/         # Container bootstrap (databases + \i sql/*.sql)
├── apps/                  # Streamlit labeling app (classification review UI)
├── tests/                 # Full pytest suite (100% passing)
├── thesis/                # Academic LaTeX manuscript and chapters
├── docker-compose.yml     # Multi-service stack (PostgreSQL, Airflow, Metabase)
└── pyproject.toml         # Python dependency management & pytest configuration
```

---

## 4. Quick Start Guide

### 1. Start the Stack

```bash
docker compose build
docker compose up -d
```

### 2. Service Endpoints

| Service | Endpoint | Purpose |
|:---|:---|:---|
| **Airflow UI** | [http://localhost:8085](http://localhost:8085) | DAG scheduling & visual pipeline monitoring (`admin`/`admin`) |
| **Metabase Monitoring** | [http://localhost:3000](http://localhost:3000) | Scraper Observability: 20-Source Health Matrix & Ingestion Alerts |
| **Streamlit Review App** | [http://localhost:8501](http://localhost:8501) | Human-in-the-loop classification review & override UI |
| **Power BI Analytics** | `localhost:5432` (`cpi_db`) | Interactive CPI Inflation Dashboards (DirectQuery / Import) |
| **PostgreSQL 16** | `localhost:5432` (`cpi_db`) | Core Warehouse hosting `bronze`, `silver`, and `gold` schemas |

### 3. Run Pipeline via Airflow

Trigger the master DAG `cpi_master_dag` in the Airflow UI or via CLI (it fans out to all 20 scraper DAGs, then `silver_dag`, then `gold_dag`):
```bash
docker compose exec airflow-scheduler airflow dags trigger cpi_master_dag
```

### 4. Execute Tests

```bash
# Run Python unit & integration tests
python -m pytest tests/ -v

# Run dbt data quality tests
docker compose exec airflow-scheduler dbt test --project-dir /opt/airflow/dbt
```
