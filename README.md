# Cambodia Daily Consumer Price Index (CPI) Medallion Pipeline
*Automated Daily Web-Scraped Inflation Tracking across 12 UN COICOP Divisions (PostgreSQL 16 · dbt · Airflow · Metabase)*

![Cambodia CPI Architecture Diagram](docs/cpi_end_to_end_architecture_diagram.jpg)

> **⚠️ Implementation Status:** The **data pipeline is live** end-to-end — scraping → Bronze ingestion → Silver cleaning / item matching / AI classification → Gold star schema. However, the **CPI index-computation layer** (Jevons elementary aggregates, imputation, Laspeyres category & headline roll-ups, GEKS-Törnqvist, Fisher Ideal) is **planned but not implemented yet**; its calculators, dbt models, and gold tables were deliberately removed until that work lands. Documents describing the full econometric methodology carry a status banner.

---

## 1. Architectural Blueprint & Tooling Matrix

| Layer | Tool | Why |
|:---|:---|:---|
| **Orchestration** | **Apache Airflow 2.9.3** | Schedules the daily `cpi_master_dag` (20 per-source scraper DAGs → `silver_dag` → `gold_dag`), handles retries, and provides automated end-to-end Medallion execution. |
| **Storage & Warehouse** | **PostgreSQL 16** (`bronze`/`staging`/`silver`/`gold` schemas) | Pure relational data warehouse hosting typed atomic raw listings, item-matching state, cleaned facts, and the analytical star schema. |
| **Transformation** | **dbt-core** (Silver & Gold) | Turns raw price records, entity-matching outputs, pack-size conversions, and COICOP classification into version-controlled, testable SQL models. |
| **Item Matching (Silver)** | **Python Service** (`ItemMatcher` with `RapidFuzz`) | Exact barcode & SKU matching with fallback token-sort fuzzy matching in Python, landing structured mappings (`silver.canonical_items`, `silver.item_match_log`). |
| **Hybrid Classification** | **AI-First Engine (dbt SQL + Gemini AI)** (`gemini-3.1-flash-lite` / `gemini-2.5-flash`) | Streamlined 4-tier ladder: human overrides (`coicop_override`), store domain purity, high-throughput Gemini cache (`silver.dim_coicop_ai_cache`, functional expression index `idx_coicop_ai_norm`), and category fallback. |
| **Index Math (Planned)** | *Not yet implemented* | The CPI computation layer — Jevons elementary aggregates, class-mean imputation, Laspeyres category & headline roll-ups, GEKS-Törnqvist multilateral splicing, Fisher Ideal substitution bias — is designed in `docs/GOLD_LAYER_IMPLEMENTATION_PLAN.md` but intentionally not built yet. Gold currently delivers the star schema only. |
| **Scraper Observability** | **Metabase v0.49** | Real-time operational monitoring: 20-Source Live Health Matrix, daily ingestion volume trends, and price anomaly alerts. |
| **Interactive Analytics** | **Microsoft Power BI** | Executive BI dashboards over the gold star schema: retailer and item-level price trends, promo analytics. Headline CPI / division index time-series are pending the index-math layer. |

---

## 2. Medallion Layer Overview

```
┌─────────────────┬───────────────────┬───────────────────────────┬──────────────────────┬───────────────────────────────┐
│   20 SOURCES    │      BRONZE       │          SILVER           │         GOLD         │         SERVING & BI          │
│                 │  (Raw Ingestion)  │     (Clean & Resolve)     │    (Star Schema)     │     (Observability & BI)      │
├─────────────────┼───────────────────┼───────────────────────────┼──────────────────────┼───────────────────────────────┤
│ AEON 1 & AEON 3 │                   │                           │                      │                               │
│ Delishop Asia   │ bronze.raw_prices │ silver.canonical_items    │ gold.dim_items       │ METABASE (Port 3000):         │
│ Ary & Samnang   ├──────────────────►│ silver.item_match_log     ├─────────────────────►│ • Executive Macro Observatory │
│ Community Pharma│ staging.exchange_ │ silver.clean_store_prices │ gold.dim_stores      │ • 12 COICOP Division Trends   │
│ Cellcard & Smart│   rates           │   (Cleaned Append / Dedup)│ gold.fct_daily_prices│ • Retailer Price & Promo BI   │
│ redBus &        │                   │ silver.classification_    │   (Conformed Fact)   │ • 20-Source Health & Ops Grid │
│  BookMeBus      │ staging.raw_      │   queue (AI triage)       │                      │ • Price Anomaly Triage Feed   │
│ Sokha & Hyatt   │   scrapes         │ staging.int_prices_cleaned│   Kimball Star       │ • Coverage & Barcode Monitors │
│ MOC Fuel (Gas)  │                   │                           │   Schema — index     │ • Scraper Health Matrix       │
│ MEF FX Daily    │ (Typed Ingestion) │ Python RapidFuzz matching │   math layer is      │                               │
│ ... (20 total)  │ Atomic & Typed    │ AI-First Gemini Flash     │   planned, not yet   │                               │
│                 │ Rows in Postgres  │ Memoized Cache Pipeline   │   implemented        │                               │
└─────────────────┴───────────────────┴───────────────────────────┴──────────────────────┴───────────────────────────────┘
```

### Bronze (Raw Ingestion & Staging)
- **Tables**: `bronze.raw_prices` (atomic typed listings with barcodes, brands, sizes, and prices), `staging.exchange_rates` (MEF USD/KHR official daily rate), `staging.raw_scrapes`.
- **Scraper Registry**: 20 production scrapers (`scrapers/sources.py`) extracting native categories, automated fallbacks, and zero-product quality gates.

### Silver (Clean, Standardize & Resolve Observations)
- **Clean Store Observations**: `silver.clean_store_prices` — unified daily appended table containing cleaned, standardized prices across all stores with exchange rates applied (KHR), unit normalization, and promo clamping.
- **Item Matching Service**: Python (`pipeline/item_matcher.py`) executing Barcode exact → SKU exact → RapidFuzz token sort ratio backed by a PostgreSQL `pg_trgm` GIN index with automated canonical UUID creation (`silver.canonical_items`, `silver.item_match_log`, `silver.needs_review`).
- **AI-First COICOP Engine**: Streamlined 4-tier daily-scoped ladder (`staging.int_coicop_classified`): human overrides -> store purity -> Gemini AI cache (`silver.dim_coicop_ai_cache`) -> native category map / fallback.
- **Operational Triage Queue**: `silver.classification_queue` captures unclassified or low-confidence items for automated Gemini re-runs or human labeling.

### Gold (Kimball Star Schema & Serving)
- **Dimensional Modeling (Star Schema)**:
  - `gold.dim_items`: Curated canonical product master dimension.
  - `gold.dim_stores`: Store & retailer master dimension.
  - `gold.fct_daily_prices`: Conformed daily price fact table at grain `(scrape_date, store_slug, item_id)` with KHR prices, unit prices, promo/outlier/fallback flags, and COICOP attribution.
- **Official Reference Data**: `gold.coicop_weights` (NIS Cambodia 12-division expenditure weights), plus anomaly tables (`gold.price_anomalies`, `gold.mart_price_anomalies`).
- **Hedonic Quality Adjustment**: Python (`pipeline/hedonic_regression.py`) fits a multi-characteristic log-linear model (RAM, Storage, Screen, Camera, 5G) for Division 08/09 electronics and writes adjusted prices to `silver.hedonic_adjusted_prices`.
- **Serving Views** (`sql/views.sql`): operational monitoring for Metabase/Airflow FDW — `gold.v_coverage`, `gold.v_monitor_scraper_daily`, `gold.v_monitor_source_health_matrix`, `gold.v_monitor_price_alerts`, `gold.v_monitor_fx_health`.

### Gold Index Layer (Planned — Not Implemented)
The CPI computation layer is designed but deliberately removed until implemented:
- Jevons elementary geometric-mean aggregates (`fct_jevons_daily` / class-mean imputation)
- Laspeyres category roll-ups (`gold.cpi_category_daily`) and headline CPI (`gold.cpi_headline_daily`)
- Multilateral GEKS-Törnqvist with movement splicing (`gold.cpi_geks_multilateral`)
- Fisher Ideal index & substitution bias (`gold.cpi_fisher_superlative`)
- 12 per-division tables and dual-currency marts (`mart_cpi_daily`, `mart_cpi_division_daily`)

Design reference: `docs/GOLD_LAYER_IMPLEMENTATION_PLAN.md`. No gold CPI index tables exist today; do not query them in dashboards.

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
│   ├── gemini_item_reviewer.py # AI & Rule-based auto-reviewer for borderline match pairs
│   ├── text_clean.py      # Text normalization for item matching
│   ├── gemini_coicop_classifier.py # Gemini AI batch classifier & cache
│   └── hedonic_regression.py # Log-linear hedonic quality adjustment
├── scripts/               # Maintenance & operational CLI utilities
│   ├── auto_review_items.py # CLI for running AI item match review queue
│   ├── warm_coicop_ai_cache.py # Pre-warms Gemini AI classification cache
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
│   ├── COICOP_MAPPING.md  # 12-Division hierarchy, store purity & classification ladder
│   ├── GOLD_LAYER_IMPLEMENTATION_PLAN.md # Econometric index formulas & gold plan
│   ├── LITERATURE_REVIEW.md # Academic foundation & comparative matrix
│   ├── PRODUCT_CLASSIFICATION_WORKFLOW.md # Pipeline lifecycle from scrape to gold
│   ├── SCRAPER_METHODOLOGY_GUIDE.md # 20 Source scraping specifications & tariffs
│   └── SILVER_LAYOUT_DESIGN.md # Silver cleaned tables & operational data model
├── sql/                   # Database DDL: schema.sql, views.sql
├── postgres-init/         # Container bootstrap (databases + \i sql/*.sql)
├── tests/                 # Full pytest suite
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
