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
│ • staging.int_coicop_classified (7-stage COICOP ladder & regex trap engine)  │
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
Stage 1 Elementary Jevons aggregation: Unweighted geometric mean prices across stores per `item_id`, baseline index comparison ($P_t / P_0 \times 100$), and day-on-day price relatives ($P_t / P_{t-1}$).

### `silver.fct_laspeyres_daily`
Stage 2 Higher-Level category aggregation: Computes category indices for all 12 COICOP divisions using official Cambodia NIS weights and day-on-day % change.

### `silver.fct_laspeyres_headline_daily`
Stage 3 Headline Laspeyres CPI roll-up across all 12 COICOP divisions in the Silver layer.

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
- **`int_coicop_classified`**: Runs the 7-stage division classification ladder (override $\to$ AI cache $\to$ traps $\to$ keyword ladder $\to$ category map $\to$ store default $\to$ unclassified). The keyword ladder is checked before the generic category map so broad store categories (aeon `Grocery` → 01) never swallow phones/toys/towels/cosmetics; confidence ranks keyword_ladder 0.950 above category_map 0.900.

---

## 5. Daily Data Management & Quality Policy

- **Idempotency**: Incremental models use `unique_key` + `on_schema_change='append_new_columns'` so re-runs are safe.
- **Strict Grain Enforcement**: Primary keys tested via dbt (`unique`, `not_null`, and `unique_combination_of_columns`).
- **Immutability of Bronze**: `bronze.raw_prices` and `staging.raw_scrapes` are append-only; corrections occur downstream in Silver.