# Pipeline Maintenance Guide

This document contains technical notes and operational guidelines for maintaining the CPI Pipeline.

---

## 1. COICOP Classification Regex

The classification pipeline uses PostgreSQL regex operators (`~*`, `!~*`) for seed evaluations and dbt intermediate transformations.

### Word Boundaries
PostgreSQL does **not** recognize the standard `\b` for word boundaries. 
- ❌ **Wrong**: `\btoothpaste\b`
- ✅ **Right**: `\ytoothpaste\y`

Using `\b` in seeds (`coicop_critical_traps.csv`, `coicop_override.csv`, etc.) will fail to match word boundaries and cause deterministic traps to fall back to lower-priority rules. Always use `\y` for start and end of word boundaries.

---

## 2. Classification Cache Resolution Precedence

In `dbt/macros/coicop_classify_macro.sql`, `silver.classification_cache` is evaluated first in `resolve_coicop_division`, `resolve_coicop_code`, and `resolve_coicop_method`.
- **Precedence Rule:** If `silver.classification_cache` contains `'UNCLASSIFIED'`, `'99'`, or `'REVIEW'`, the macro treats this entry as a miss and lets the resolution cascade down to:
  1. `ov_exact_div` (Exact Overrides)
  2. `purity_division` (Store Purity e.g. PPWSA, EDC, Khmer24, Realestate)
  3. `trap_div` (Critical Traps)
  4. `ai_div` (Gemini AI Drill-Down)
  5. Fallbacks (Global Overrides, Text Rules, Category Map, Store Defaults)
- **Incremental Re-Evaluation:** In `dbt/models/silver/intermediate/int_coicop_classified.sql`, existing records previously classified by AI or lower-priority methods are re-evaluated if their canonical name matches an active pattern in `coicop_critical_traps`.

---

## 3. PostgreSQL Parallel Workers & Shared Memory

When running large incremental joins in `int_prices_cleaned.sql` on constrained Docker hosts:
- **Shared Memory:** `docker-compose.yml` configures `shm_size: 1g` for the `postgres` service.
- **Worker Configuration:** `int_prices_cleaned.sql` contains a `pre_hook: ["SET max_parallel_workers_per_gather = 0"]` to prevent `could not resize shared memory segment` errors during large multi-table hash joins.

---

## 4. Hedonic Quality Adjustment Engine

`pipeline/hedonic_regression.py` calculates quality-adjusted constant-spec prices for electronics (COICOP `09`):
- **Primary Engine:** Uses `statsmodels.api.OLS` for log-linear regression when available.
- **Zero-Downtime Analytical Fallback:** If `statsmodels` is not installed, the module automatically uses an analytical Ordinary Least Squares solver via `numpy.linalg.lstsq` (`(X^T X)^-1 X^T y`) with identical parameter naming, R² formulation, and baseline specification adjustments.
- **Airflow Non-Blocking Behavior:** In `orchestration/dags/silver_dag.py`, unexpected errors raise `AirflowSkipException` to ensure the Silver data pipeline remains resilient and does not block downstream gold transformations.

---

## 5. Airflow Performance & Concurrency Tuning

To prevent worker CPU saturation during 25-scraper fan-outs:
- **Scraper Slug Decoupling (`scrapers/sources/slugs.py`):**
  Airflow DAGs (`cpi_master_dag.py`, `scraper_dags.py`) must import `SCRAPER_SLUGS` from `scrapers.sources.slugs`, NOT `SCRAPER_REGISTRY`. This prevents the scheduler from executing 25 dynamic scraper imports, third-party libraries, and browser drivers on every 30-second DAG parsing loop. Latency is ~1s (down from 100s).
- **Concurrency Guards:**
  - `AIRFLOW__CORE__PARALLELISM=8`
  - `AIRFLOW__CORE__MAX_ACTIVE_TASKS_PER_DAG=6`
  - `max_active_runs=1` on all scraper DAGs.
- **Clearing Stuck or Queued Runs via CLI:**
  ```bash
  # Clear a stuck task instance
  docker compose exec airflow-scheduler airflow tasks clear <dag_id> -t <task_id> -s <start_date> -e <end_date> -y
  ```

---

## 6. Purging and Batch Classifying Unclassified Items

If any canonical items ever enter `silver.canonical_items` with null or unclassified COICOP codes:
1. **Automated Dual-Query Classifier:**
   `pipeline/gemini_coicop_classifier.py` checks both `match_method = 'new_item'` AND existing unclassified/empty codes.
2. **Batch Classification CLI:**
   Run the batch hierarchical classifier utility:
   ```bash
   python scripts/run_hierarchical_classification.py --limit 1000
   ```
3. **Verification Query (Postgres):**
   ```sql
   SELECT COUNT(*) 
   FROM silver.canonical_items 
   WHERE coicop_code IS NULL 
      OR coicop_code LIKE '%.unclassified';
   ```
   Must always return `0`.

---

## 7. Official NIS Benchmark Ingestion & Tracking Error Maintenance

Official monthly CPI figures published by the National Institute of Statistics (NIS) provide the ground-truth benchmark for evaluating the high-frequency scraped nowcaster.

### Automated Weekly Scraper
* **Airflow DAG**: `nis_cpi_dag` runs every Monday at 08:00 AM ICT (`0 8 * * 1`).
* **Scraper Module**: `pipeline/nis_cpi_importer.py` scans `https://nis.gov.kh/សន្ទស្សន៍ថ្នាក់ជាតិ/` for monthly Excel releases (`CPI-12-group-*.xlsx`).
* Extracts Headline Index, Core Index, MoM %, YoY %, and all 12 COICOP division indices.

### Manual or Ad-Hoc Ingestion CLI
```bash
# Automated portal fetch:
python -m pipeline.nis_cpi_importer --scrape-portal

# Or manual single month entry:
python -m pipeline.nis_cpi_importer --cpi-month 2026-09-01 --headline 220.15 --mom 0.52 --yoy 5.34
```

### dbt Seed & Tracking Error Model Refresh
```bash
dbt seed --select nis_official_cpi
dbt run --select fct_cpi_nis_comparison
```

### Metabase Dashboard Provisioning & Diagnostics
To provision or refresh all 3 canonical Metabase dashboards with interactive filters and latest cards:
```bash
python scripts/setup_metabase_dashboards.py
```

Run the unit tests verifying dashboard parameters and template tag mappings:
```bash
pytest tests/test_setup_metabase_dashboards.py -v
```

Run the live database diagnostic audit script to verify all dashboard query cards against PostgreSQL:
```bash
python scripts/test_metabase_cards.py
```

---

## 8. Circuit Breaker Dual-Currency Price Velocity Normalization

`pipeline/circuit_breaker.py` guards against corrupt data ingestion by checking rolling volume drops and price velocities against 7-day clean medians from `silver.clean_store_prices`.

### Dual-Currency Alignment
Because `silver.clean_store_prices` stores prices in **Khmer Riel (KHR)** (`price_khr`), incoming raw records from USD-denominated retailers (e.g. Delishop, Cellcard, Hyatt, Sokha) must be converted to KHR before price velocity checks:
```python
rate = self.get_exchange_rate(scrape_date)
# If raw record currency is 'USD', price is multiplied by rate before computing incoming median
```
- **Exchange Rate Source:** Dynamically fetched from `staging.exchange_rates` on `scrape_date`, falling back to `4,050.0 KHR/USD` if missing.
- **Audit Logging:** Events evaluated are permanently logged to `ops.circuit_breaker_events` with status (`PASSED`, `WARNING_FLAGGED`, `HALTED`), record count, median price, price velocity delta %, and payload details.

---

## 9. Scraper DOM Selectors & Graceful Degradation Maintenance

When retailers update their frontend templates, follow these verified operational protocols:

### Cellcard Mobile (`scrapers/sources/cellcard.py`)
- **Live Selector:** Parses Next.js App Router rendered `<h4>` headings and parent plan containers on `https://www.cellcard.com.kh/en/mobile` for AO Mobile 5G/4G, Student, Gamer, and Big Love plans.
- **Regex Extraction:** Extracts pricing via `\$\s*(\d+(\.\d+)?)`, data allowances via `(\d+\s*GB)`, and validity periods via `(\d+\s*Days?)`. Captures 25 live mobile plans dynamically.
- **Fallback Cascade:** If DOM cards change, falls back automatically to `CELLCARD_MOBILE_PLANS` baseline with `is_fallback=True`.

### Metfone Cambodia (`scrapers/sources/metfone.py`)
- **Next.js Proxy API:** Queries `POST https://metfone.com.kh/api/proxy/packages/config-des-packages` (`wsCode: getConfigDesPackages`) for live KADO Plus packages.
- **Catalog Merge:** Merges live packages with complementary baseline plans (Social, Entertainment, Education, Fiber) to guarantee complete 14-item basket representation.

### Smart Cambodia (`scrapers/sources/smart.py`)
- **Live Plan Extraction:** Scrapes live flagship plans directly from `https://www.smart.com.kh/plans/smart-laor` (`Smart Laor! Data 1`, `1.5`, `6`, `10`, `Rean Monthly`) using multiline regex across React Server Component chunks.
- **Fallback Cascade:** Falls back to `SMART_MOBILE_PLANS` baseline for broader tiers and fiber broadband plans.

### Khmer Moto Shop (`scrapers/sources/khmermoto.py`)
- **Public Anakut REST API:** Direct unauthenticated JSON query to `https://system.anakutapp.com/ecommerce/public/api/products?store_code=KMT&row_per_page=100&page=1` pulling the full 187-item motorcycle and spare parts catalog.

### Khmer24 Real Estate (`scrapers/sources/khmer24.py`)
- **Nuxt SSR Offset Pagination:** Khmer24 utilizes infinite scroll driven by `?offset={(page - 1) * 30}` rather than `?page={page}`.
- **Rate-Limiting:** Maintain randomized delays (1.0–2.0s) between offset requests to adhere to anti-scraping policies.

### Khmer Samnang Phone Shop (`scrapers/sources/samnangshop.py`)
- **WooCommerce Store API:** Target `https://khmersamnang.com/wp-json/wc/store/v1/products?per_page=100`.
- **Catalog Size:** Active listings reflect current in-stock catalog (e.g. 75 items following inventory audits). All active products are captured in a single paginated query.

### Bayon BKK (`scrapers/sources/bayonbkk.py`)
- **Anti-Bot Graceful Degradation:** Foodpanda/PerimeterX blocks live scrapers with HTTP 403 (`px-captcha`). In adherence to scraping ethics (never bypassing CAPTCHA), the scraper gracefully engages `BAYON_MENU_BASELINE` (`is_fallback=True`).

