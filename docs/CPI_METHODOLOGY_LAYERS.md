# CPI Methodology — Layer-by-Layer Detail

> **[!WARNING]**
> **IMPLEMENTATION STATUS (2026-08):** The Gold-layer index computation described in parts of this document — Jevons elementary aggregates, imputation, Laspeyres category/headline roll-ups, GEKS-Tornqvist, Fisher Ideal — is **planned but NOT implemented yet**. Its calculators, dbt models, and gold tables were removed from the codebase.
> Currently live: Bronze ingestion; Silver cleaning / item matching / AI classification / hedonic adjustment; Gold star schema (dim_items, dim_stores, fct_daily_prices); monitoring views. See README "Implementation Status".

**Status:** ⚠️ Partially Implemented — Layers 1–3 live (Bronze/Silver/classification); index layers (Jevons/Laspeyres/GEKS/Fisher) **planned, not implemented**  
**Date:** 2026-08-26  
**Project:** Cambodia CPI Pipeline (`D:\CPI PIPELINE`)  
**Companion docs:** `CPI_METHODOLOGY.md` (summary) · `COICOP_MAPPING.md` (classification) · `BASKET_V1_DRAFT.md` (basket)

---

# Layer 1 — Data Source

## 1.1 Scope & Properties
Captures daily prices across 19 online sources + official MEF USD/KHR exchange rates.
- **Density**: Up to 35,000 observations per day.
- **Storage**: Append-only PostgreSQL `staging.raw_scrapes` (canonical JSONB payloads stamped with a UUID `run_id`); clean typed listings in `bronze.raw_prices`.
- **Quality Gates**: Price bounds validation per source (`canonical.PRICE_BOUNDS`) and zero-product failure guards (`pipeline/bronze_ingestion.py`).

---

# Layer 2 — Sampling & Selection

## 2.1 Basket Selection
- Scrapes the full reachable population across 19 sources (20 source DAGs incl. MEF FX).
- Filters applied in Silver/Gold:
  - `cpi_eligible = TRUE` (excludes non-goods sources like real estate and hotels).
  - `is_fallback = FALSE` (excludes static catalogue fallbacks).
  - `price_khr > 0` and `is_outlier = FALSE`.

---

# Layer 3 — Item Identity & Elementary Aggregation

## 3.1 Item Resolution Ladder (`pipeline/item_matcher.py`)
1. **Barcode exact**: Barcode match ($\ge 8$ digits) maps to same canonical `item_id` in `silver.canonical_items`.
2. **SKU exact**: Store-native SKU resolution maps to canonical identity via `silver.dim_canonical_products`.
3. **Fuzzy Name**: RapidFuzz `token_sort_ratio >= 0.95` auto-accepts to existing canonical item.
4. **New Item**: Unmatched items (<0.95) automatically generate a new deterministic UUID canonical item.

Every decision is audited in `silver.item_match_log` (`raw_price_id → item_id`, `match_method`, `confidence`).

## 3.2 Clean Store Prices (1 Store 1 Table Paradigm in Silver)
- `silver.clean_store_prices`: Standardized daily price quotes partitioned per store and source. Preserves store-level quote attributes with KHR conversion, promo clamping, unit price standardization, and COICOP tagging.

## 3.3 Conformed Star Schema (`gold.*`)
- `gold.dim_items`: Master dimension — one row per canonical product across all stores with canonical name, brand, barcode, size, native category, store coverage, and resolved COICOP division.
- `gold.dim_stores`: Curated dimensional master of all 20 Cambodian retailers and utility sources.
- `gold.fct_daily_prices`: Primary price fact table — one row per `(scrape_date, store_slug, item_id)`; contains essential price facts, `unit_price_khr` (kg/L), discount metrics, and quality flags.

---

# Layer 4 — Higher-Level Aggregation (Laspeyres & Gold Marts)

## 4.1 Division & Headline Indices
- Gold 12 Division Tables (`gold.cpi_div01_food` to `gold.cpi_div12_misc`): Dedicated tables providing granular product-level price tracking, base indices, and metrics for each of the 12 COICOP divisions.
- Headline Laspeyres Roll-Up:
  $$\text{CPI}_t = \sum_{g \in \text{present}} I_{g,t} \times \left( \frac{W_g}{\sum_{j \in \text{present}} W_j} \right)$$
  Persisted into `gold.cpi_headline_daily` (`formula = 'Laspeyres'`).

## 4.2 Official NIS Cambodia Division Weights (`dbt/seeds/category_weights.csv`)
| Division | Name | Official Weight |
|---|---|---|
| 01 | Food and non-alcoholic beverages | 44.800% |
| 02 | Alcoholic beverages, tobacco and narcotics | 1.500% |
| 03 | Clothing and footwear | 2.900% |
| 04 | Housing, water, electricity, gas and other fuels | 17.100% |
| 05 | Furnishings, household equipment and routine household maintenance | 3.300% |
| 06 | Health | 5.600% |
| 07 | Transport | 12.200% |
| 08 | Communication | 3.900% |
| 09 | Recreation and culture | 1.900% |
| 10 | Education | 1.500% |
| 11 | Restaurants and hotels | 3.100% |
| 12 | Miscellaneous goods and services | 2.200% |
| **Total** | **All 12 Divisions** | **100.000%** |

---

# Layer 5 — Multilateral Methods (GEKS-Törnqvist)

## 5.1 Engine Implementation (`pipeline/geks_calculator.py`)
- Executes across a 13-period rolling window over `gold.fct_daily_price_stats`.
- Calculates all pairwise bilateral ratios $T_{j,t}$ and produces base-invariant, drift-free multilateral indices:
  $$\text{GEKS}_t = \prod_{j \in W} (T_{j,t})^{1 / |W|}$$
- Persisted into `gold.cpi_geks_multilateral` (`formula = 'GEKS-Tornqvist'`).

---

# Layer 6 — Quality Adjustment & Outliers

## 6.1 Pack Size & Unit Price Conversion
- Raw strings (e.g. `24Pack x 25g`, `380ML`, `1.5 L`) parsed via regex into standardized base units (kg, L) in `int_prices_cleaned.sql`.
- Derived `unit_price_khr` prevents shrinkflation / pack-size changes from distorting the price relative.

## 6.2 Anomaly & Outlier Controls
- Promo discounts clamped to $[0\%, 95\%]$ (`int_prices_cleaned.sql`).
- Prices $\le 0$ dropped at Silver.
- Quotes deviating $> 10\times$ from median flagged `is_outlier = TRUE`.
- Day-on-day shifts $> 15\%$ recorded in `gold.fct_price_anomalies` (`SPIKE_UP` / `CRASH_DOWN`).

---

# Layer-by-Layer Status Matrix

| Layer | Component | Status | Implementation Artifact |
|---|---|---|---|
| **1** | Data Source | ✅ Done | `scrapers/*` (`SCRAPER_REGISTRY`), `staging.raw_scrapes`, `staging.exchange_rates`, MinIO raw snapshots |
| **2** | Basket / Selection | ✅ Done | Silver filters (`cpi_eligible`, `is_fallback`), `BASKET_V1_DRAFT.md` |
| **3** | Item Identity | ✅ Done | `pipeline/item_matcher`, `silver.item_match_log`, `silver.clean_store_prices`, `gold.dim_items`, `gold.fct_daily_prices` |
| **—** | COICOP Classification | ✅ Done | dbt `int_coicop_classified`, `pipeline.gemini_coicop_classifier`, `silver.dim_coicop_ai_cache` |
| **4** | Laspeyres Aggregation | ⚠️ Planned | `gold.cpi_category_daily`, `gold.cpi_headline_daily` — tables/models removed until implemented |
| **5** | GEKS Multilateral | ⚠️ Planned | `pipeline/geks_calculator.py`, `gold.cpi_geks_multilateral` — removed until implemented |
| **6** | Quality Adjustment | ⚠️ Partial | Hedonic regression live (`silver.hedonic_adjusted_prices`); anomaly mart has no writer yet |
| **Serving** | Presentation & Ops | ✅ Partial | Metabase (`gold.v_*` monitoring views); Power BI index models pending index layer |
