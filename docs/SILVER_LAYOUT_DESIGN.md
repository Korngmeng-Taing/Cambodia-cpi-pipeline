# Silver Layer Design — Store-Level Cleaned Tables for CPI

> **[!NOTE]**
> **Current Pipeline Architecture:** Live end-to-end with **3-Key Load-Balanced Multi-Key Pool**, **768-dim Vector Embeddings + Deterministic Spec Guards**, **4-Tier 12-Division COICOP Semantic Classifier**, and **Gold Star Schema**. Historical data is backfilled from August 18 onwards.

**Status:** ✅ Active — Conformed Silver Data Model in PostgreSQL 16 (`cpi_db`)  
**Schema:** `silver.*` (Clean Store Tables & System Control) + `staging.*` (Intermediate Transformations) + `gold.*` (Conformed Star Schema & Marts)  
**Diagrams:** Refer to [`docs/ARCHITECTURE_DIAGRAMS.md`](ARCHITECTURE_DIAGRAMS.md) for full visual schema representations.

---

## 1. Core Architectural Principle

The Medallion architecture strictly separates store-level observation data hygiene (Silver) from conformed multidimensional star schema analytics (Gold):
- **Silver Layer (Clean Store Prices & Resolution):** Preserves source grain and isolation. Scraped prices are parsed, currency-converted to KHR, promo-clamped, outlier-tagged, unit-standardized, deduplicated via vector embeddings + spec guards, and classified into standardized clean store observations (`silver.clean_store_prices`).
- **Gold Layer (Conformed Star Schema & Marts):** Houses the conformed dimensional model (`gold.dim_items`, `gold.dim_stores`, `gold.fct_daily_prices`), monitoring views, and downstream CPI index calculation engines.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             SILVER ARCHITECTURE                             │
├───────────────────────────────┬─────────────────────────────────────────────┤
│ 1. SYSTEM & OPERATIONAL       │ 2. CLEAN STORE-LEVEL PRICE TABLES           │
│    (Audit & Control Tables)   │    (Clean Store Quotes & Observations)      │
├───────────────────────────────┼─────────────────────────────────────────────┤
│ • silver.canonical_items      │ ──► silver.clean_store_prices               │
│ • silver.item_match_log       │     (Per-store clean quotes & observations) │
│ • silver.dim_coicop_ai_cache  │                                             │
│ • silver.classification_queue │ ──► Feeds Gold Star Schema (gold.*)         │
│ • silver.needs_review         │                                             │
│ • silver.hedonic_adjusted_    │                                             │
│   prices                      │                                             │
├───────────────────────────────┴─────────────────────────────────────────────┤
│ 3. INTERMEDIATE TRANSFORMATIONS (Built in silver schema)                    │
│ • silver.int_prices_cleaned (USD->KHR, promo clamping, unit standardization) │
│ • silver.int_coicop_classified (4-tier hybrid vector & AI COICOP ladder)    │
└─────────────────────────────────────────────────────────────────────────────┘

```

---

## 2. Silver Layer Clean Price Tables

### `silver.clean_store_prices`
Unified clean daily store price observations table:
- Preserves raw observation granularity (`raw_price_id`, `store_slug`, `scrape_date`, `item_id`).
- Standardized KHR pricing via official daily MEF exchange rates.
- Promotion indicators (`discount_pct`, `on_promo`), standardized package units (`size_value`, `size_unit`, `unit_price_khr`), and quality flags (`is_outlier`, `cpi_eligible`).
- Assigned COICOP division (`coicop_division`, `coicop_code`, `coicop_method`, `coicop_confidence`).

---

## 3. System & Operational Tables

### `silver.canonical_items`
Deterministic UUID canonical identity master maintained automatically by `pipeline/item_matcher.py` & `pipeline/vector_item_matcher.py`. Contains normalized canonical names, brand, barcode, size, and inherited COICOP codes.

### `silver.item_match_log`
Full audit trail mapping `raw_price_id` $\to$ `item_id` with match method (`barcode_exact`, `sku_exact`, `fuzzy_text`, `vector_embedding`, `new_item`) and confidence score ($0.000$–$1.000$).

### `silver.dim_coicop_ai_cache`
Persistent memoization cache for Gemini AI classifications (`gemini-2.5-pro` / `gemini-2.5-flash`). Prevents duplicate API calls across daily runs.

### `silver.needs_review`
Dedicated table for borderline fuzzy/vector match candidates ($0.75 \le \text{confidence} < 0.88$). Auto-reviewed by `pipeline/vector_item_matcher.py` and `pipeline/gemini_item_reviewer.py` via:
1. **Deterministic Spec Guards (`is_spec_compatible`):** Checks hardware/spec conflicts (Storage GB, RAM, pack size, volume tolerance $\le 10\%$) to reject false merges (`SPLIT_NEW`).
2. **Gemini Pro/Flash AI Arbitration:** Resolves ambiguous variants (`APPROVE_MATCH` vs `SPLIT_NEW`) and updates `silver.item_match_log`.

### `silver.hedonic_adjusted_prices`
Stores quality-adjusted constant-specification prices for Division 08 and 09 electronics. Evaluates multi-attribute characteristics (`ram_gb`, `storage_gb`, `screen_inches`, `camera_mp`, `is_5g`) against a trailing baseline to purge pure technological progress from genuine price inflation.

---

## 4. Multi-Key Pool & Hybrid COICOP Classification

- **Multi-Key Pool (`pipeline/key_pool.py`):** Rotates 3+ Gemini API keys in thread-safe round-robin sequence to achieve $4,500$ daily requests, $45$ RPM, and automatic 429 quota failover.
- **Hybrid COICOP Engine (`pipeline/hybrid_embeddings_classifier.py`):**
  1. *Tier 1:* Human authority overrides (`coicop_override.csv`).
  2. *Tier 2:* 15 Pure Store Domain Locks (Gasoline $\to$ 07, Telecom $\to$ 08, Housing $\to$ 04) resolved in $0.001\text{ms}$.
  3. *Tier 3:* 768-dim Vector Cosine Similarity against the 12 UN COICOP reference category vectors (separates Community Pharma *Panadol* $\to$ 06 from *Cetaphil/Shampoo* $\to$ 12, and resolves AEON multi-division listings).
  4. *Tier 4:* Gemini Pro AI fallback for ambiguous cases ($<0.72$), permanently cached in Postgres.
