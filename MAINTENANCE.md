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
