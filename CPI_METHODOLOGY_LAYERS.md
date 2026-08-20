# CPI Methodology — Layer-by-Layer Detail

**Status:** ✅ Fully Implemented (Layers 1–6 active, PostgreSQL 16 + Airflow + dbt)  
**Date:** 2026-08-17  
**Project:** Cambodia CPI Pipeline (`D:\CPI PIPELINE`)  
**Companion docs:** `CPI_METHODOLOGY.md` (summary) · `COICOP_MAPPING.md` (classification) · `BASKET_V1_DRAFT.md` (basket)

---

# Layer 1 — Data Source

## 1.1 Scope & Properties
Captures daily prices across 19 online sources + official MEF USD/KHR exchange rates.
- **Density**: Up to 35,000 observations per day.
- **Storage**: Append-only PostgreSQL `staging.raw_scrapes` (canonical JSONB payloads stamped with a UUID `run_id`); clean rows in `bronze.raw_prices`; immutable raw snapshots on MinIO (`s3://cpi-bronze/{store}/dt={date}/raw.json`) + Parquet cold archive.
- **Quality Gates**: Price bounds validation per source (`canonical.PRICE_BOUNDS`) and zero-product failure guards (`pipeline/bronze_ingestion.py`).

---

# Layer 2 — Sampling & Selection

## 2.1 Basket Selection
- Scrapes the full reachable population across 19 sources (20 source DAGs incl. MEF FX).
- Filters applied in Silver/Gold:
  - `cpi_eligible = TRUE` (excludes non-goods sources like real estate and hotels).
  - `is_fallback = FALSE` (excludes static catalogue fallbacks).
  - `price_khr > 0` and `is_outlier = FALSE`.
- Base Period fixed at `base_period = '2026-08'` (dbt var / `BASE_PERIOD` env). Base prices are bootstrapped **once and frozen** per base period: `gold.sp_ensure_base_prices` (called by `gold_dag`) skips the bootstrap once rows exist, so historical indices never shift from silent re-anchoring. Force a re-baseline manually with `gold.sp_bootstrap_base_prices`.

---

# Layer 3 — Item Identity & Elementary Aggregation

## 3.1 Item Resolution Ladder (`pipeline/item_matcher.py`)
1. **Barcode exact**: Barcode match ($\ge 8$ digits) maps to same canonical `item_id` in `silver.canonical_items`.
2. **SKU + Brand + Size**: Links via store-native mapping (stubbed until schema provides it).
3. **Fuzzy Name**: RapidFuzz `token_sort_ratio >= 0.95` (auto-accept) or `0.85 <= score < 0.95` (sent to `silver.needs_review`).
4. **New Item**: Deterministic UUID canonical item.

Every decision is audited in `silver.item_match_log` (`raw_price_id → item_id`, `match_method`, `confidence`).

## 3.2 Jevons Geometric Mean (`silver.fct_jevons_daily` & `gold.fct_daily_price_stats`)
For each `item_id` on `scrape_date`:
$$P_{i,t} = \exp\left( \frac{1}{N_{i,t}} \sum_{s=1}^{N_{i,t}} \ln(\text{price}_{i,s,t}) \right)$$
- `silver.fct_jevons_daily`: Computes elementary geometric mean prices, base price relatives ($P_t / P_0 \times 100$), and day-on-day price relatives ($P_t / P_{t-1}$) directly in the Silver layer.
- `gold.fct_daily_price_stats`: Imputes missing items forward $\le 7$ days (LOCF) and persists elementary price stats for Gold aggregation.

## 3.3 Conformed Daily Fact & Dimensions (`silver.dim_items`, `silver.fct_daily_prices`)
- `silver.dim_items`: One row per canonical product across all stores with canonical name, brand, barcode, size, native category, and resolved COICOP division.
- `silver.fct_daily_prices`: One row per `(scrape_date, store_slug, item_id)`; `unit_price_khr` is standardized per base metric unit (kg/L) with promo clamping and quality flags. Missing items are forward carried $\le 7$ days in `silver.fct_daily_prices_imputed`.

---

# Layer 4 — Higher-Level Aggregation (Laspeyres)

## 4.1 Division & Headline Indices
- Silver Category Aggregation (`silver.fct_laspeyres_daily`): Aggregates elementary Jevons price relatives geometrically per COICOP division with day-on-day % change.
- Silver Headline Roll-Up (`silver.fct_laspeyres_headline_daily`): Daily Headline Laspeyres CPI in Silver.
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
| **3** | Item Identity & Jevons | ✅ Done | `pipeline/item_matcher`, `silver.item_match_log`, `silver.dim_items`, `gold.fct_daily_price_stats` |
| **—** | COICOP Classification | ✅ Done | dbt `int_coicop_classified`, `silver.coicop_override`, `apps/labeling_app.py` |
| **4** | Laspeyres Aggregation | ✅ Done | `gold.cpi_category_daily`, `gold.cpi_headline_daily`, `gold.category_weights` |
| **5** | GEKS Multilateral | ✅ Done | `pipeline/geks_calculator.py`, `gold.cpi_geks_multilateral` |
| **6** | Quality Adjustment | ✅ Done | `int_prices_cleaned` unit conversion, promo clamp, `gold.fct_price_anomalies` |
| **Serving** | Presentation & Ops | ✅ Done | Metabase (`gold.v_*` views), Streamlit UI, `orchestration/config/*.py` |
