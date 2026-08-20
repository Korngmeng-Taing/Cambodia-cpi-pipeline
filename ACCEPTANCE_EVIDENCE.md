# Cambodia CPI Pipeline — Acceptance Evidence & Verification Matrix

This document verifies the implementation against the design specifications and methodology requirements.

---

## 1. System Acceptance Verification Matrix

| Requirement / Component | Design Spec Reference | Verification Command | Status | Evidence / Target |
|---|---|---|---|---|
| **Canonical Bronze Schema v1.0** | Bronze §3 (`SCRAPER_METHODOLOGY_GUIDE.md`) | `pytest tests/test_canonical.py` | ✅ PASS (7/7) | `normalize_records()` / `validate_records()` conform to the canonical contract. |
| **Bronze Ingestion & Gates** | Bronze §1 | `pytest tests/test_bronze_ingestion.py` | ✅ PASS (6/6) | Zero-product guard, bounds validation, `staging.raw_scrapes` append + DQ gate. |
| **BronzeScraper Batch Writer** | Bronze §2 | `pytest tests/test_bronze_scraper.py` | ✅ PASS (4/4) | `write_canonical_batch` + FX rate storage. |
| **MinIO Raw Object Storage** | Bronze §1.4 | `pytest tests/test_minio_storage.py` | ✅ PASS (3/3) | `s3://cpi-bronze/{store}/dt={date}/raw.json` put/get + local fallback. |
| **Parquet Cold Archive** | Bronze §1 | `pytest tests/test_parquet_archiver.py` | ✅ PASS (3/3) | Partitioned `year=/month=/date=/{store}.parquet` archives. |
| **Item Resolution Ladder** | Silver §3.1 | `pytest tests/test_item_matcher.py` | ✅ PASS (6/6) | Barcode exact → fuzzy ≥ 0.95 (review 0.85-0.94) → new UUID item; `item_match_log` audit. |
| **Scraper Sources & Registry** | Bronze §2 | `pytest tests/test_sources.py tests/test_scrapers.py` | ✅ PASS (29/29) | 20 sources in `SCRAPER_REGISTRY` with native category extraction and fallbacks. |
| **Hybrid Gemini AI Classification** | Silver §3 | `pytest tests/test_gemini_coicop_classifier.py` | ✅ PASS (9/9) | Memoized `dim_coicop_ai_cache` + structured JSON mode + review queue resolution. |
| **Hedonic Quality Adjustment** | Silver §3 | `pytest tests/test_hedonic_regression.py` | ✅ PASS (5/5) | Specs extraction (RAM/Storage) + OLS quality-adjusted price computation. |
| **GEKS-Törnqvist Multilateral** | Methodology §5 | `pytest tests/test_geks_calculator.py` | ✅ PASS (4/4) | Bilateral Törnqvist + transitive 13-period GEKS; transitivity/circularity verified. |
| **Elementary Jevons & Laspeyres Indices** | Methodology §3 & §4 | `pytest tests/test_cpi_indices.py` | ✅ PASS (5/5) | Jevons geometric mean properties, 100% weight sum, and all 12 Gold division tables verified. |
| **Full Python Test Suite** | All components | `pytest tests/ -v` | ✅ PASS (100/100) | Unit and integration test suite across all pipeline services, scrapers, and math engines, incl. `test_pipeline_contracts.py` (6 regression guards on headline reweighting, unit-price-aware Jevons, base-price freeze, GEKS wiring, observed-only inflation). |
| **dbt Silver Data Quality** | dbt models & tests | `dbt run --select silver && dbt test --select silver` | ✅ PASS (31/31 tests) | 100% classification coverage, `test_price_sanity`, `test_unit_math`, `test_traps`, `test_coicop_coverage`, `test_idempotency`. All 31 gates green after materializing `dim_stores` + `fct_daily_prices_imputed`. |
| **dbt Gold Data Quality & 12 Divisions** | dbt models & tests | `dbt run --select gold && dbt test --select gold` | ✅ PASS (17 models) | not_null / uniqueness / `> 0` / accepted-values gates on Gold models and 12 COICOP division tables. |
| **Official COICOP Weights** | Methodology §4.2 | `SELECT SUM(weight_pct) FROM gold.coicop_weights;` | ✅ PASS | Exactly 100.000% across 12 divisions (`category_weights` seed). |
| **Laspeyres Headline CPI** | Methodology §4 | `SELECT * FROM gold.cpi_headline_daily ORDER BY scrape_date DESC LIMIT 1;` | ✅ PASS | `index_value = Σ index_value × (weight / Σ weight_present)` (renormalised over present divisions), `formula='Laspeyres'`. Guarded by `test_headline_formula_is_reweighted_over_present` (2026-08-20 fix). |
| **12 Dedicated Division Views** | Gold §4 | `SELECT count(*) FROM gold.cpi_div01_food ...` | ✅ PASS (12/12) | Individual tables populated across all 12 COICOP divisions with clean item-level tracking. |
| **GEKS Output Table** | Methodology §5 | `SELECT * FROM gold.cpi_geks_multilateral ORDER BY scrape_date DESC LIMIT 1;` | ✅ PASS | 13-period transitive index persisted with `matched_items_count`. Wired into `gold_dag` (`geks_multilateral_calc`) 2026-08-20; daily rolling GEKS persisted, monthly GEKS best-effort. |
| **Metabase BI Integration** | Serving | HTTP GET `http://localhost:3000` | ✅ PASS | Connected to `gold.v_cpi_latest`, `gold.v_inflation`, `gold.v_inflation_observed`, `gold.v_top_movers`, and 12 division tables. |
| **Human Labeling App** | Ops | `streamlit run apps/labeling_app.py` | ✅ PASS | Interactive triage of `silver.classification_queue` into overrides and category maps. |

---

## 2. Trap Products Compliance Checklist

- [x] `COOKING WINE 750ML` $\rightarrow$ **01** (Food and non-alcoholic beverages)
- [x] `SOMERSBY CIDER 4X330ML` $\rightarrow$ **02** (Alcoholic beverages)
- [x] `WOLF BLASS SHIRAZ 750ML` $\rightarrow$ **02** (Alcoholic beverages)
- [x] `TVHC SLIPPER UNISEX` $\rightarrow$ **03** (Clothing and footwear)
- [x] `ELECTRICITY PREPAID TOPUP` $\rightarrow$ **04** (Housing and utilities)
- [x] `LIX FLOOR CLEANER 3.8L` $\rightarrow$ **05** (Household equipment and maintenance)
- [x] `TV COFFEE FILTER 40` $\rightarrow$ **05** (Household equipment)
- [x] `GREEN ONION SLICER` $\rightarrow$ **05** (Household equipment)
- [x] `TOPVALU BEST PRICE DETERGENT` $\rightarrow$ **05** (Household equipment)
- [x] `PARACETAMOL 500MG 20TABS` $\rightarrow$ **06** (Health)
- [x] `FISHERMEN'S FRIEND MENTHOL` $\rightarrow$ **06** (Health)
- [x] `LITTLE TREES BLACK ICE AIR FRESHENER` $\rightarrow$ **07** (Transport)
- [x] `LITTLE TREES WASH&WAX` $\rightarrow$ **07** (Transport)
- [x] `PETROL 95 1L` $\rightarrow$ **07** (Transport)
- [x] `SMARTPHONE 15 128GB` / `IPHONE 15` $\rightarrow$ **08** (Communication)
- [x] `MY-RING NOTES A5` $\rightarrow$ **09** (Recreation and culture)
- [x] `ENGLISH TUTOR CLASS` $\rightarrow$ **10** (Education)
- [x] `WAKAME MIXED RICE WITH SALMON` $\rightarrow$ **11** (Restaurants and hotels)
- [x] `SHRIMP RICE PAPER ROLL` $\rightarrow$ **11** (Restaurants and hotels)
- [x] `SUNPLAY SKIN AQUA SPF50` $\rightarrow$ **12** (Miscellaneous goods and services)
- [x] `LIPICE LIP BALM` $\rightarrow$ **12** (Miscellaneous goods and services)
- [x] `COTTON PADS FOR MAKEUP REMOVAL` $\rightarrow$ **12** (Miscellaneous goods and services)
- [x] `LIGHT BLUE-EARLOOP FACEMASK` $\rightarrow$ **06** (Health — protective mask)
- [x] `EAR LOOP FACE MASK BOX` $\rightarrow$ **06** (Health — protective mask)
- [x] `PURELABEL MASK SHEET PACK (ALOE ESSENCE)` $\rightarrow$ **12** (Miscellaneous — cosmetics)
- [x] `DOVE SUGAR COCONUT BODY SCRUB` $\rightarrow$ **12** (Miscellaneous — personal care)
- [x] `BON BONS SHOWER BATH FOAM MILKY CUPCAKE` $\rightarrow$ **12** (Miscellaneous — personal care)

> These trap rules are enforced by `dbt/tests/test_traps.sql` against the classification pipeline. Masks/scrubs/foams were re-verified on 2026-08-19 after the cosmetic-guard + medical-mask fix: 226 such items → 12, protective masks → 06, zero leakage into 01/03.

---

## 3. End-to-End Execution Proof

To run the complete suite and verify acceptance end-to-end:
```bash
# 1. Start full container stack
docker compose up -d

# 2. Execute Python unit and integration tests (all tests except test_dbt_connection.py
#    which requires a reachable Postgres host)
docker compose exec airflow-webserver pytest /opt/airflow/tests/ -v

# 3. Trigger sequential master pipeline (20 scraper DAGs → silver → gold)
docker compose exec airflow-webserver airflow dags trigger cpi_master_dag

# 4. Run dbt data quality gates
docker compose exec airflow-webserver dbt test --project-dir /opt/airflow/dbt
```