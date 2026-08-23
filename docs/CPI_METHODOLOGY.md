# CPI Index Methodology — Scraped-Data Path

**Status:** ✅ Fully Implemented (Layers 1–6 active, PostgreSQL 16 + Airflow + dbt)  
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
| **Silver** | `silver.canonical_items`, `silver.item_match_log`, `silver.dim_items`, `silver.dim_stores`, `silver.fct_daily_prices`, `silver.fct_daily_prices_imputed`, `silver.fct_jevons_daily`, `silver.fct_laspeyres_daily`, `silver.fct_laspeyres_headline_daily` | `pipeline.item_matcher` (RapidFuzz) + dbt models & views | EAN/Fuzzy item resolution; 0–95% promo clamp; unit-price derivation; COICOP classification ladder (`int_coicop_classified`); Jevons elementary relatives & Laspeyres category aggregation. |
| **Silver Triage** | `silver.needs_review`, `silver.classification_queue`, `silver.coicop_override` | `apps/labeling_app.py` (Streamlit) | Human-in-the-loop triage for REVIEW / low-confidence items. |
| **Gold (Index & Divisions)** | `gold.base_prices`, `gold.fct_daily_price_stats`, `gold.cpi_category_daily`, `gold.cpi_headline_daily`, `gold.cpi_div01_food` ... `gold.cpi_div12_misc`, `gold.cpi_geks_multilateral` | dbt Gold models + Airflow `gold_dag` + `pipeline.geks_calculator` | Jevons elementary aggregation; Laspeyres weighting; 12 dedicated COICOP division tables; GEKS multilateral index; anomaly detection. |
| **Serving** | `gold.v_cpi_latest`, `gold.v_inflation`, `gold.v_inflation_observed`, `gold.v_top_movers`, `gold.v_promo_impact`, `gold.v_coverage` | Metabase (`:3000`) | Executive dashboards, inflation trajectories (incl. observed-only DoD inflation), and store coverage monitoring. |

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
- **Weights**: `dbt/seeds/category_weights.csv` (materialized to `gold.category_weights`) — 12 divisions summing to 100.000%.
- **Classification**: 9-tier daily-scoped ladder in `int_coicop_classified.sql` — human overrides (`coicop_override.csv` + `silver.coicop_override_manual`) → store purity → Gemini AI cache (AI-first, `silver.dim_coicop_ai_cache`) → global overrides → traps → keyword rules (`coicop_keywords.csv`, two-tier) → `silver.coicop_category_map` → weak keywords/store defaults. See `COICOP_MAPPING.md`.
- **Tariffs**: `dbt/seeds/utility_tariffs.csv` (materialized to `silver.utility_tariffs`) — regulated EDC electricity + PPWSA water fixed prices for Division `04` (see `SCRAPER_METHODOLOGY_GUIDE.md` §5).
