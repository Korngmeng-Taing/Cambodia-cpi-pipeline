# Silver Layer Design — Relational Tables for CPI

**Status:** ✅ Active — Conformed Medallion Star Schema in PostgreSQL 16 (`cpi_db`)  
**Schema:** `silver.*` (Curated Core) + `staging.*` (Intermediate Transformations & Raw) + dbt Models

---

## 1. Core Architectural Principle

The Silver layer is structured into three clean tiers to prevent table clutter in downstream BI (Metabase) while preserving full auditability and modularity:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             SILVER ARCHITECTURE                             │
├───────────────────────────────┬─────────────────────────────────────────────┤
│ 1. SYSTEM & OPERATIONAL       │ 2. CURATED SERVING CORE (Metabase-Facing)   │
│    (Audit & Control Tables)   │    (Conformed Kimball Dimensional Model)    │
├───────────────────────────────┼─────────────────────────────────────────────┤
│ • silver.canonical_items      │ ──► silver.dim_items (Canonical products)   │
│ • silver.item_match_log       │ ──► silver.dim_stores (Store metadata)      │
│ • silver.dim_coicop_ai_cache  │ ──► silver.fct_daily_prices (Daily quotes)  │
│ • silver.needs_review         │ ──► silver.fct_daily_prices_imputed         │
│ • silver.classification_queue │                                             │
├───────────────────────────────┴─────────────────────────────────────────────┤
│ 3. INTERMEDIATE TRANSFORMATIONS (Built in staging schema)                    │
│ • staging.int_prices_cleaned (USD->KHR, promo clamping, unit standardization)│
|  - staging.int_coicop_classified (9-tier daily-scoped COICOP ladder: purity + rules-as-data + gated AI cache)  |
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Curated Serving Core (The True Silver)

These are the primary conformed models exposed for analytics and Metabase reporting:

### `silver.dim_items`
Unified canonical item master dimension (one row per `item_id`):
- `canonical_name`, `brand`, `barcode`, `size_norm`, `native_category`.
- `coicop_division` resolved from classification ladder.
- `unit_of_measure`, `store_count`, `avg_match_confidence`, lifecycle timestamps (`first_seen`, `last_seen`, `is_active`).

### `silver.dim_stores`
Unified retailer & source dimension (one row per `store_slug`):
- `store_name`, `source_type`, `channel`, `default_currency`, `default_coicop_division`.
- `total_observations`, `distinct_products_count`, `first_scraped_at`, `last_scraped_at`.

### `silver.fct_daily_prices`
Primary daily price fact table (grain: `scrape_date`, `store_slug`, `item_id`):
- Cleaned and classified price quote (`price_khr`, `unit_price_khr`).
- Promotion indicators (`discount_pct`, `on_promo`), standardized units (`size_value`, `size_unit`), and quality flags (`is_outlier`, `cpi_eligible`).

### `silver.fct_daily_prices_imputed`
Daily fact view with $\le 7$-day forward price carry for temporarily missing products.

### `silver.fct_jevons_daily`
Elementary Jevons aggregation: Unweighted geometric mean prices across stores ($P_{\text{Jevons}}$) per `item_id`, standardized geometric unit prices, quote counts, and store density metrics.

---

## 3. System & Operational Tables

These tables manage entity matching, AI memoization, and human-in-the-loop review queues:

### `silver.canonical_items`
Deterministic UUID5 canonical identity master maintained by `pipeline/item_matcher.py`.

### `silver.item_match_log`
Full audit trail mapping `raw_price_id` $\to$ `item_id` with match method (`barcode_exact`, `sku_exact`, `fuzzy_text`, `new_item`) and confidence score ($0.000$–$1.000$).

### `silver.dim_coicop_ai_cache`
Persistent memoization cache for Gemini AI classifications. Prevents duplicate LLM API calls across daily runs.

### `silver.needs_review`
Low-confidence product matches ($0.70$–$0.89$) routed here for human triage via `apps/labeling_app.py`.

### `silver.classification_queue`
Active triage queue capturing unclassified items for automated Gemini AI batch processing and manual tagging.

---

## 4. Intermediate Transformation Layer (`staging.*`)

To keep the `silver` schema clean for BI tools:
- **`int_prices_cleaned`**: Performs USD $\to$ KHR currency conversion, promo clamping ($[0\%, 95\%]$), unit pricing math (per kg / per L), and $\pm 3\sigma$ outlier detection.
- **`int_coicop_classified`**: Runs the 9-tier daily-scoped classification ladder (exact/per-store overrides $\to$ store purity $\to$ gated AI cache $\to$ global overrides $\to$ traps $\to$ keyword STRONG rules from `coicop_keywords.csv` priority <300 $\to$ category map $\to$ keyword WEAK rules + store defaults $\to$ unclassified). STRONG keywords outrank the generic category map so broad store categories (aeon `Grocery` → 01) never swallow phones/toys/towels/cosmetics; WEAK food rules sit *below* the map. Only the current run's `scrape_date` is classified each day; historical rows are preserved for index stability.

---

## 5. Daily Data Management & Quality Policy

- **Idempotency**: Incremental models declare `unique_key` and use the `delete+insert` strategy (`on_schema_change='append_new_columns'`), along with defensive classification CTE deduplication (`DISTINCT ON (item_id, store_slug)`), so re-runs are strictly idempotent. dbt-postgres defaults to `append`, which silently ignores `unique_key` - every incremental model must set the strategy explicitly.
- **Strict Grain Enforcement**: Primary keys tested via dbt (`unique`, `not_null`, `test_idempotency`).
- **Immutability of Bronze**: `bronze.raw_prices` is append-only per observation, backed since migration 011 by a DB-level unique index (`uq_raw_prices_observation`) matching the scraper's re-scrape dedup key; `staging.raw_scrapes` keeps one upserted batch record per store per day. Corrections occur downstream in Silver.
