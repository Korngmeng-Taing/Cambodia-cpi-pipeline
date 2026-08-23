# CPI Pipeline Explained — Simple Guide with Examples

**Goal:** Turn messy daily scrapes from 20 Cambodian online sources into a clean, auditable, high-frequency Consumer Price Index (CPI).

**The big idea — a 3-layer relational architecture on PostgreSQL 16 (Medallion):**

```
 SCRAPERS (20 sources: 19 retail/service/fuel + MEF FX)
       │
       ▼
 1. BRONZE  ──► staging.raw_scrapes (append-only JSONB + UUID run_id)
       │        bronze.raw_prices (clean rows for dbt)
       ▼
 2. SILVER  ──► Python ItemMatcher → silver.canonical_items / item_match_log
       │        dbt models: dim_items, dim_stores, fct_daily_prices, fct_daily_prices_imputed
       │        Hybrid COICOP Engine (Rule Ladder + Gemini AI Cache)
       ▼
 3. GOLD    ──► gold.base_prices, fct_daily_price_stats, cpi_category_daily,
       │        cpi_headline_daily, cpi_geks_multilateral
       │
       ├──► METABASE  ──► Executive Inflation Dashboards & Visual Charts (:3000)
       └──► STREAMLIT ──► Human-in-the-loop Classification Review UI (:8501)
```

Orchestration: **Airflow 2.9.3** — `cpi_master_dag` runs daily at 06:00 Asia/Phnom_Penh, fans out to one DAG per source (20 total), then `silver_dag`, then `coicop_classification_dag`, then `gold_dag`.

This guide follows one bag of rice through the entire journey.

---

## Part 1 — Scrape → Bronze (Ingestion)

Every night at `06:00`, `cpi_master_dag` triggers each store's scraper DAG. The scraper reads product cards and returns a list of raw dicts.

**Example — what AEON returns (raw):**

```json
{
  "name": "PREMIUM DAUN KEO RICE 5KG",
  "price": 20300,
  "originalPrice": 24300,
  "categoryId": 125,
  "productId": "34821",
  "badge": ["/img/badge/dry.png"]
}
```

Before anything is saved, `normalize_record()` (`pipeline/canonical.py`) reshapes it into the **canonical contract** (Schema v1.0):

```json
{
  "scrape_date": "2026-08-17",
  "source_slug": "aeon",
  "source_type": "grocery",
  "store": "AEON 1 Phnom Penh",
  "currency": "KHR",
  "cpi_eligible": true,
  "item_id": "34821",
  "barcode": null,
  "name": "PREMIUM DAUN KEO RICE 5KG",
  "category_native": "Grocery",
  "price": 20300,
  "original_price": 24300,
  "discount_pct": null,
  "on_promo": true,
  "promo": {"type": "fix", "value": 4000, "start": null, "end": null},
  "url": "https://aeonmall.com.kh/...",
  "is_fallback": false,
  "source": "scrape",
  "scraped_at": "2026-08-17T18:32:11Z",
  "attrs": {},
  "brand": null,
  "quantity": null,
  "package_size": null,
  "unit": null,
  "is_out_of_stock": false
}
```

`pipeline/bronze_ingestion.py::ingest_source_bronze()` runs the full Bronze path per source:
1. **Fetch & normalize**: `SCRAPER_REGISTRY[source].fetch_records()` → `canonical.normalize_records()` (Schema v1.0).
2. **Zero-product guard**: A scrape returning 0 records raises before any DB write.
3. **Price Bounds Validation**: Prices validated against source-specific bounds before persistence.
4. **PostgreSQL writes**: `staging.raw_scrapes` (append-only JSONB + UUID `run_id`); MEF FX routed to `staging.exchange_rates`.

### Quality Gates Before Persisting to Staging
1. **Schema validation**: Rows must satisfy the canonical contract; invalid rows are dropped/flagged.
2. **Price bounds**: Prices must fall inside the store's `(min, max)` band (`canonical.PRICE_BOUNDS`).
3. **Zero-product guard**: If a scraper returns 0 items, the task raises an error to prevent empty ingestion.
4. **Append with UUID `run_id`**: The entire batch is inserted into `staging.raw_scrapes` alongside audit metadata.
5. **Bronze DQ gate**: `check_bronze_gate()` verifies a non-empty `staging.raw_scrapes` row exists per source/date.

---

## Part 2 — Bronze → Silver (Item Matching + dbt)

The `silver_dag` runs two steps:

### Step 1: Item Resolution (`pipeline/item_matcher.py`, RapidFuzz)
1. **Barcode exact** ($\ge 8$ digits) → same canonical `item_id`.
2. **SKU + brand + size** → store-native mapping.
3. **Fuzzy name**: RapidFuzz `token_sort_ratio >= 0.95` auto-accepts; `0.85 <= score < 0.95` routes to `silver.needs_review`.
4. **New item**: Mints a deterministic UUID5 canonical item.

Every decision is written to `silver.item_match_log` (`raw_price_id → item_id`, `match_method`, `confidence`); canonical products live in `silver.canonical_items`. Low-confidence matches go to `silver.needs_review` for human triage.

### Step 2: dbt Silver models & Analytical Views
1. **`int_prices_cleaned`** (intermediate) — USD $\to$ KHR currency conversion via MEF FX, promo math (discount clamped to $[0\%, 95\%]$), price bounds, unit-price derivation.
2. **`int_coicop_classified`** (intermediate) — daily-scoped 9-tier COICOP ladder: exact/per-store overrides → store purity → AI cache (gated) → global overrides → traps → keyword STRONG (`coicop_keywords.csv`) → category map → keyword WEAK/store defaults → UNCLASSIFIED.
3. **`dim_items`** — canonical item dimension with prioritized COICOP division selection.
4. **`dim_stores`** — retailer and source dimension across 20 Cambodian sources.
5. **`fct_daily_prices`** — primary daily fact table (one row per item/store/date with cleaned price, unit price, promo indicators).
6. **`fct_daily_prices_imputed`** — conformed daily fact view with $\le 7$-day forward price carry.
7. **`silver.fct_jevons_daily`** — Stage 1 Elementary Jevons geometric mean prices, base relatives ($P_t / P_0 \times 100$), and day-on-day relative changes.
8. **`silver.fct_laspeyres_daily`** — Stage 2 Higher-Level category aggregation across the 12 COICOP divisions using official NIS weights.
9. **`silver.fct_laspeyres_headline_daily`** — Stage 3 National Headline Laspeyres CPI in the Silver layer.
10. **`classification_queue`** — operational triage queue for unclassified products.

Example — price cleaning for the 5kg bag of rice:
$$\text{Discount} = \frac{24300 - 20300}{24300} \times 100 = 16.46\%$$

Unit price normalization:
$$\text{unit\_price\_khr} = \frac{20300}{5.0} = 4{,}060 \text{ KHR/kg}$$

---

## Part 3 — Silver → Gold (dbt SQL + Stored Procedures + Python GEKS)

The `gold_dag` runs `sp_calculate_daily_cpi`, then `dbt run --select gold`, then the Python GEKS step, then `dbt test`.

### Step 1: Base Prices (`gold.base_prices`, dbt & procedure)
Geometric mean price per item over the base period (var `base_period`, default `2026-08`):
$$P_{i,0} = \exp\left( \frac{1}{N_{i,0}} \sum \ln(\text{price}_{i,0}) \right)$$

### Step 2: Jevons Elementary Aggregation (`gold.fct_daily_price_stats`)
Geometric mean price per item per scrape date across qualifying stores:
$$P_{i,t} = \exp\left( \frac{1}{N_{i,t}} \sum \ln(\text{price}_{i,t}) \right)$$

### Step 3: 12 Dedicated COICOP Division Tables (`gold.cpi_div01_food` to `gold.cpi_div12_misc`)
Dedicated tables exposing granular product-level price tracking, base indices, and metrics for each of the 12 COICOP divisions:
- `gold.cpi_div01_food` (Food & Non-Alcoholic Beverages)
- `gold.cpi_div02_alcohol_tobacco` (Alcohol & Tobacco)
- `gold.cpi_div03_clothing_footwear` (Clothing & Footwear)
- `gold.cpi_div04_housing_utilities` (Housing, Water, Electricity, Gas)
- `gold.cpi_div05_furnishings` (Furnishings & Routine Maintenance)
- `gold.cpi_div06_health` (Health & Pharmaceuticals)
- `gold.cpi_div07_transport` (Transport & Intercity Bus)
- `gold.cpi_div08_communication` (Communication & Mobile/WiFi)
- `gold.cpi_div09_recreation` (Recreation, Culture & Pet Care)
- `gold.cpi_div10_education` (Education)
- `gold.cpi_div11_restaurants_hotels` (Restaurants & Accommodation)
- `gold.cpi_div12_misc` (Miscellaneous Goods & Personal Care)

### Step 4: Division Index & Headline Laspeyres CPI (`gold.cpi_category_daily`, `gold.cpi_headline_daily`)
Weighted roll-up across active divisions using `category_weights` seed (sums to 100.000%):
$$\text{CPI}_t = \sum_{g \in \text{present}} I_{g,t} \times \left( \frac{W_g}{\sum W_{\text{present}}} \right)$$

### Step 5: Multilateral GEKS-Törnqvist (`pipeline/geks_calculator.py`)
Python (`numpy`/`pandas`) computes a 13-period rolling window transitive index over `gold.fct_daily_price_stats`:
$$\text{GEKS}_t = \exp\left( \frac{1}{|W|} \sum_{j \in W} \ln(T_{j,t}) \right)$$
where $T_{j,t}$ is the bilateral Törnqvist relative over matched items. Persisted to `gold.cpi_geks_multilateral` (eliminates chain drift from product churn).

### Step 6: Price Anomalies (`gold.fct_price_anomalies`)
Day-on-day shifts $> 15\%$ flagged as `SPIKE_UP` / `CRASH_DOWN`.

---

## Part 4 — Serving & Operations

- **Metabase Dashboards** ([http://localhost:3000](http://localhost:3000)): Visualizes `gold.v_cpi_latest`, `gold.v_inflation`, `gold.v_promo_impact`, `gold.v_top_movers`, and the 12 COICOP division tables.
- **Streamlit Review UI** ([http://localhost:8501](http://localhost:8501)): Interactive triage of `silver.classification_queue` / `silver.needs_review` into `silver.coicop_override`.
- **Airflow Orchestration** ([http://localhost:8085](http://localhost:8085)): Master DAG `cpi_master_dag` coordinating 20 scrapers $\to$ Silver $\to$ COICOP AI $\to$ Gold in strict order.
- **Ops utilities** (`orchestration/config/`): `clear_all_history.py`, `cleanup_dead_dags.py`.
