# Cambodia CPI Computation Pipeline

A production-grade **Consumer Price Index (CPI)** computation pipeline built on a **Medallion Architecture** (Bronze → Silver → Gold) with PostgreSQL 16, Apache Airflow 2.9.3, dbt-core, and MinIO object storage.

---

## 1. Architectural Blueprint & Tooling Matrix

| Layer | Tool | Why |
|:---|:---|:---|
| **Orchestration** | **Apache Airflow 2.9.3** | Schedules the daily `cpi_master_dag` (20 per-source scraper DAGs → `silver_dag` → `coicop_classification_dag` → `gold_dag`), handles retries, and provides automated end-to-end Medallion execution. |
| **Storage** | **PostgreSQL 16** (`staging`/`silver`/`gold` schemas) + **MinIO** (`s3://cpi-bronze`) + **Parquet** (cold archive in MinIO) | PostgreSQL holds raw scrapes, item-matching state, and all CPI tables; MinIO stores immutable raw JSON snapshots per store/day + partitioned Parquet cold archives. |
| **Transformation** | **dbt-core** (Silver & Gold) | Turns item-matching outputs, native category hierarchies, Jevons calculations, pack-size conversions, and COICOP weighted roll-ups into version-controlled, testable SQL models with full auditability. |
| **Item Matching (Silver)** | **Python Service** (`ItemMatcher` with `RapidFuzz`) | Exact barcode & SKU matching with fallback token-sort fuzzy matching in Python, landing structured mappings (`silver.canonical_items`, `silver.item_match_log`) for dbt consumption. |
| **Hybrid Classification** | **Rule Engine (dbt SQL)** + **Gemini AI** (`gemini-3.1-flash-lite`) | Rules resolve ~95%–98% of items instantly using a 7-stage ladder (override → AI cache → trap exceptions → keyword ladder → category map → store default). The keyword ladder runs before the generic category map and a personal-care guard pins cosmetics to 12 while medical masks route to 06; Gemini AI resolves remaining edge cases with memoization in `silver.dim_coicop_ai_cache`. |
| **Index Math (Silver & Gold)** | **dbt SQL** + **Python** (`GEKSCalculator`) | dbt SQL & Postgres views compute elementary Jevons prices (`silver.fct_jevons_daily`), Laspeyres category & headline aggregations (`silver.fct_laspeyres_daily`, `gold.cpi_headline_daily`), and 12 dedicated Gold COICOP division tables (`gold.cpi_div01_food` to `gold.cpi_div12_misc`). Python computes rolling 13-period multilateral GEKS-Törnqvist indices (`gold.cpi_geks_multilateral`). |

---

## 2. Medallion Layer Overview

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 MEDALLION ARCHITECTURE                                 │
├─────────────────┬───────────────────┬───────────────────────────┬──────────────────────┤
│   20 SOURCES    │      BRONZE       │          SILVER           │         GOLD         │
│                 │  (Raw Ingestion)  │     (Clean & Resolve)     │    (CPI Indices)     │
├─────────────────┼───────────────────┼───────────────────────────┼──────────────────────┤
│ AEON 1 & AEON 3 │                   │                           │                      │
│ Delishop Asia   │ staging.raw_scrapes│ silver.canonical_items   │ gold.base_prices     │
│ Ary & Samnang   ├──────────────────►│ silver.item_match_log    ├─────────────────────►│
│ Community Pharma│ staging.exchange_ │ silver.dim_items         │ gold.fct_daily_price │
│ Cellcard & Smart│   rates           │ silver.fct_daily_prices  │   _stats (Jevons)    │
│ redBus &        │                   │ silver.fct_jevons_daily  │ gold.cpi_category    │
│  BookMeBus      │ MinIO raw JSON    │   (Elementary Relatives)  │   _daily (COICOP)    │
│ Sokha & Hyatt   │  s3://cpi-bronze  │ silver.fct_laspeyres     │ gold.cpi_headline    │
│ MOC Fuel (Gas)  │ Parquet cold      │   _daily (12 Divisions)   │   _daily (Laspeyres) │
│ MEF FX Daily    │ Append-Only       │ silver.fct_laspeyres     │ gold.cpi_div01_food  │
│ ... (20 total)  │ Immutable         │   _headline_daily        │   ... to div12_misc  │
│                 │                   │ Python RapidFuzz matching │ gold.cpi_geks        │
│                 │                   │ Hybrid Gemini AI Fallback │   _multilateral      │
└─────────────────┴───────────────────┴───────────────────────────┴──────────────────────┘
```

### Bronze (Raw Ingestion & Cold Storage)
- **Tables**: `staging.raw_scrapes` (append-only JSONB payloads + UUID `run_id`), `staging.exchange_rates` (MEF USD/KHR official daily rate).
- **Object Storage**: MinIO raw snapshots `s3://cpi-bronze/{store}/dt={YYYY-MM-DD}/raw.json` + partitioned Parquet archives (`s3://cpi-bronze/parquet/month=YYYY-MM/date=YYYY-MM-DD/{store}.parquet`).
- **Scraper Registry**: 20 production scrapers (`scrapers/sources.py`) extracting native categories, automated fallbacks, and zero-product quality gates. `AEON_MAX_PAGES=0` enables full catalog scraping across all ~17,000 products.

### Silver (Clean, Resolve & Elementary Aggregation)
- **Item Matching Service**: Python (`pipeline/item_matcher.py`) executing Barcode exact → SKU exact → RapidFuzz token sort ratio (auto-accept $\ge 0.95$, review queue $0.85 - 0.94$, new canonical item creation) writing `silver.canonical_items` / `silver.item_match_log`.
- **Hybrid COICOP Engine**: 7-stage ladder (`int_coicop_classified.sql`) — override → AI cache → trap exceptions → keyword ladder → category map → store default → UNCLASSIFIED — with a personal-care guard (cosmetics → 12, medical masks → 06).
- **Elementary Jevons & Laspeyres Views**:
  - `silver.fct_jevons_daily`: Computes store-unweighted geometric mean prices ($P_{\text{Jevons}}$), base price comparisons ($P_t / P_0 \times 100$), and day-on-day price relatives ($P_t / P_{t-1}$).
  - `silver.fct_laspeyres_daily`: Category-level aggregation across the 12 COICOP divisions using official Cambodia NIS weights.
  - `silver.fct_laspeyres_headline_daily`: Daily Headline Laspeyres CPI in the Silver layer.

### Gold (Serving, 12 Division Tables & Multilateral Aggregation)
- **12 Dedicated Division Tables**: `gold.cpi_div01_food` through `gold.cpi_div12_misc` exposing granular product price trends, base indices, and metrics per COICOP division.
- **Headline CPI & Elementary Stats**: `gold.base_prices` (August 2026 reference prices), `gold.fct_daily_price_stats` (LOCF gap-filled geometric mean prices), `gold.cpi_category_daily`, and `gold.cpi_headline_daily`.
- **Python GEKS**: Multilateral GEKS-Törnqvist service (`pipeline/geks_calculator.py`) calculating a 13-period rolling window transitive index across matched items, persisted to `gold.cpi_geks_multilateral`.

---

## 3. Repository Layout

```
CPI PIPELINE/
├── scrapers/              # Python scraper modules (Bronze ingestion)
│   ├── base.py            # Abstract BaseScraper interface
│   ├── sources.py         # SCRAPER_REGISTRY (19 sources + MEF FX)
│   └── sample_store.py    # Sample store scraper
├── pipeline/              # Core pipeline services
│   ├── bronze_ingestion.py# Bronze ingestion entrypoint (fetch → normalize → MinIO → DB)
│   ├── bronze_scraper.py  # BronzeScraper batch writer & FX store
│   ├── canonical.py       # Canonical Bronze Schema v1.0 normalize/validate
│   ├── minio_storage.py   # MinIO/S3 raw JSON + Parquet object storage client
│   ├── parquet_archiver.py# Cold storage Parquet archiver
│   ├── item_matcher.py    # Silver item matching service (RapidFuzz)
│   ├── text_clean.py      # Text normalization for item matching
│   └── geks_calculator.py # Gold multilateral GEKS-Törnqvist service
├── dbt/                   # dbt-core transformation project
│   ├── dbt_project.yml
│   ├── profiles.yml
│   ├── models/
│   │   ├── bronze/        # Bronze staging verification
│   │   ├── staging/       # Source views on raw tables
│   │   ├── silver/        # Incremental Silver models & tests
│   │   └── gold/          # Gold elementary & aggregation models
│   ├── seeds/             # Category weights, COICOP overrides & utility tariffs
│   ├── tests/             # Singular price sanity, traps & idempotency tests
│   └── macros/            # Custom schema mapper
├── orchestration/         # Airflow orchestration stack
│   ├── Dockerfile         # Unified container image (Airflow 2.9.3 + deps)
│   ├── dags/              # cpi_master_dag, scraper_dags, silver_dag, coicop_classification_dag
│   ├── config/            # Ops scripts (rebuild_silver, clear_all_history, ...)
│   ├── plugins/           # Custom Airflow plugins
│   └── logs/              # Task logs
├── sql/                   # Legacy DDL: schema.sql, views.sql, gold_procedures.sql
├── postgres-init/         # Container bootstrap (databases + \i sql/*.sql)
├── apps/                  # Streamlit labeling app (classification review UI)
├── metabase/              # Metabase dashboard exports
├── tests/                 # Full pytest suite (unit & integration tests)
├── docker-compose.yml     # Services: Postgres, MinIO, Airflow, dbt, Metabase
└── pyproject.toml         # Python dependency management
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
| **Airflow UI** | [http://localhost:8085](http://localhost:8085) | DAG scheduling & visual monitoring (`airflow`/`airflow`) |
| **MinIO Console** | [http://localhost:9001](http://localhost:9001) | Raw scrape object storage (`minioadmin`/`minioadmin`) |
| **Metabase BI** | [http://localhost:3000](http://localhost:3000) | Analytics dashboards & charts |
| **PostgreSQL 16** | `localhost:5432` (`cpi_db`) | Warehouse hosting `bronze`, `silver`, `gold` schemas |

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
