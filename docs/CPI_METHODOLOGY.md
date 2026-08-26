# CPI Index Methodology — Scraped-Data Path

> **[!WARNING]**
> **IMPLEMENTATION STATUS (2026-08):** The Gold-layer index computation described in parts of this document - Jevons elementary aggregates, imputation, Laspeyres category/headline roll-ups, GEKS-Tornqvist, Fisher Ideal - is **planned but NOT implemented yet**. Its calculators, dbt models, and gold tables were removed from the codebase.
> Currently live: Bronze ingestion; Silver cleaning / item matching / AI classification / hedonic adjustment; Gold star schema (dim_items, dim_stores, fct_daily_prices); monitoring views. See README "Implementation Status".

**Status:** ⚠️ Partially Implemented — Layers 1–3 live (Bronze/Silver/classification); index layers (Jevons/Laspeyres/GEKS/Fisher) **planned, not implemented**  
**Date:** 2026-08-17  
**Applies to:** Cambodia CPI Pipeline (`D:\CPI PIPELINE`) — Bronze (`staging.*`, `bronze.*`) $\rightarrow$ Silver (`silver.*`) $\rightarrow$ Gold (`gold.*`)

---

## 1. System Architecture & Six-Layer Overview

The Cambodia CPI pipeline implements all six methodological layers required for high-frequency e-commerce inflation measurement:

```
L1  Scraped e-commerce listings (20 sources: 19 retail/service/fuel sources + MEF USD/KHR daily rate)
        ↓
L2  Full-population scrape → Basket selection (cpi_eligible=TRUE, is_fallback=FALSE)
        ↓
L3  Jevons elementary price per item across stores (unit-price aware)
        ↓
L4  Laspeyres higher-level aggregation over official NIS COICOP division weights
        ↓
L5  GEKS-Törnqvist multilateral aggregation over 13-period rolling window (drift-free)
        ↓
L6  Quality adjustment: pack-size / unit-price conversion & overlap methods
```

---

## 2. Medallion Layer Mapping (PostgreSQL 16)

| Layer | Physical Storage | Implementation | Role |
|---|---|---|---|
| **Bronze (Raw)** | `staging.raw_scrapes`, `staging.exchange_rates`, `bronze.raw_prices` | Airflow `scrape_{source}_dag` + `pipeline.bronze_ingestion` | Append-only raw JSONB with UUID `run_id`, zero-product guards, bounds validation; atomic daily quote ingestion. |
| **Silver (1 Store 1 Table)** | `silver.clean_store_prices`, `silver.canonical_items`, `silver.item_match_log` | `pipeline.item_matcher` (RapidFuzz) + dbt models (`int_prices_cleaned`, `clean_store_prices`) | Store-level clean quotes (1 store 1 table paradigm); EAN/Fuzzy item resolution; 0–95% promo clamp; unit-price derivation; COICOP classification ladder (`int_coicop_classified`). |
| **Silver Triage** | `silver.classification_queue`, `silver.dim_coicop_ai_cache`, `silver.coicop_override_manual` | `pipeline/gemini_coicop_classifier.py` + `pipeline/gemini_item_reviewer.py` | Automated AI classification with Gemini Flash memoization cache and unclassified triage queue. |
| **Gold (Star Schema & Dimensions)** | `gold.dim_items`, `gold.dim_stores`, `gold.fct_daily_prices` | dbt Gold models + Airflow `gold_dag` | Conformed Star Schema dimensional model (Master item dimensions, Store metadata dimension, Daily price facts with unit-pricing). |
| **Serving Views** | `gold.v_coverage`, `gold.v_monitor_scraper_daily`, `gold.v_monitor_source_health_matrix`, `gold.v_monitor_price_alerts`, `gold.v_monitor_fx_health` | Metabase (`:3000`) | Executive observability dashboards, daily scraper health, price anomaly alerts, exchange rate monitor, and store coverage. |

---

## 3. Mathematical Formulas

### Layer 3 — Elementary Price (Jevons)
For item $i$ on date $t$, the elementary price is the geometric mean over qualifying quotes (`dbt/models/gold/fct_daily_price_stats.sql`):
$$P_{i,t} = \exp\left( \frac{1}{N_{i,t}} \sum_{s=1}^{N_{i,t}} \ln(\text{price}_{i,s,t}) \right)$$
*Qualifying criteria:* `cpi_eligible = TRUE`, `is_fallback = FALSE`, `is_outlier = FALSE`, `price_khr > 0`. When package sizes vary, the unit price (per kg / per litre) is used.

> **Unit-price-aware selection & Class-Mean Imputation:** the elementary price is taken over **unit prices** (per-kg/L) whenever *every* quote for that item/day carries a comparable base dimension; otherwise it falls back to the shelf price. For missing items ($\le 7$ days), **Class-Mean Imputation** (ILO standard) adjusts the last observed price using the geometric average movement of observed items in its COICOP division.

### Layer 3 — Elementary Price Relative
$$I_{i,t} = \left( \frac{P_{i,t}}{P_{i,0}} \right) \times 100$$
where $P_{i,0}$ is the base price from `gold.base_prices` (`base_period = '2026-08'`, dbt var).

### Layer 4 — Laspeyres Higher-Level Aggregation
Division index for COICOP group $g$ (`gold.cpi_category_daily`):
$$I_{g,t} = \exp\left( \frac{1}{|g|} \sum_{i \in g} \ln(I_{i,t}) \right)$$

Overall Headline CPI (`gold.cpi_headline_daily`):
$$\text{CPI}_t = \sum_{g \in \text{present}} I_{g,t} \times \left( \frac{W_g}{\sum_{j \in \text{present}} W_j} \right)$$
using official NIS division weights ($W_g$) from the `category_weights` seed, summing to $100.000\%$.

> **Weight renormalisation:** the headline always reweights the official weights to the divisions present on a given day (`weight_pct / Σ weight_present`), matching the dbt and Silver-layer implementations.

### Layer 5 — Multilateral GEKS-Törnqvist & Superlative Fisher
Eliminates chain drift from high product churn using a 13-period rolling window $W$ with **Movement Splicing** (`pipeline/geks_calculator.py`):
$$\text{GEKS}_t = \prod_{j \in W} (T_{j,t})^{1 / |W|} = \exp\left( \frac{1}{|W|} \sum_{j \in W} \ln(T_{j,t}) \right)$$
Movement Splicing links the window movement to previous published indices without historical number revisions:
$$I_t^{\text{Published}} = I_{t-1}^{\text{Published}} \times \frac{\text{GEKS}_{W_t}(t)}{\text{GEKS}_{W_t}(t-1)}$$

Additionally, the **Superlative Fisher Ideal Index** ($I_{\text{Fisher}} = \sqrt{I_{\text{Laspeyres}} \times I_{\text{Paasche}}}$) is calculated in `pipeline/fisher_calculator.py` to quantify **Consumer Substitution Bias** ($\text{Bias} = I_{\text{Laspeyres}} - I_{\text{Fisher}}$).

### Layer 6 — Quality Adjustment & Hedonics
- **Unit Price Normalization**: Automatic conversion of raw package sizes to base metric units (`KHR/kg` or `KHR/L`) protects against shrinkflation.
- **Hedonic Quality Adjustment**: OLS log-linear hedonic regression ($\ln(\text{Price}) = \beta_0 + \beta_1 \text{RAM} + \beta_2 \text{Storage}$) adjusts Division 09/08 consumer electronics prices to holding quality constant (`pipeline/hedonic_regression.py` $\to$ `silver.hedonic_adjusted_prices`).
- **Operational Price Anomalies**: Single-pass `LAG()` window flags day-on-day shifts $> 15\%$ into `gold.mart_price_anomalies`.

---

## 4. Reference Tables

- **Base period**: `base_period` dbt var, default `2026-08` (set via `BASE_PERIOD` env).
- **Classification**: Streamlined 4-tier daily-scoped ladder in `int_coicop_classified.sql` — human overrides (`coicop_override.csv` + `silver.coicop_override_manual`) → store domain purity → Gemini AI cache (AI-first, `silver.dim_coicop_ai_cache`) → store native category map / defaults. See `COICOP_MAPPING.md`.
- **Tariffs**: `dbt/seeds/utility_tariffs.csv` (materialized to `silver.utility_tariffs`) — regulated EDC electricity + PPWSA water fixed prices for Division `04` (see `SCRAPER_METHODOLOGY_GUIDE.md` §5).

