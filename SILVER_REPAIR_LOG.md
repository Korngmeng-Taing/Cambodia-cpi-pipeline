# Silver Layer Repair & Architecture Evolution Log

**Status:** ✅ COMPLETE — Fully Migrated to PostgreSQL 16 Simple Stack  
**Date:** 2026-08-17  

---

## 1. Migration to Simple PostgreSQL 16 Architecture (2026-08-17)

### Problem with Legacy Lakehouse Stack
- Multi-component brittleness: Trino view dialect conflicts (`spark` vs `trino`), Iceberg REST catalog schema repair needs, JVM memory pressure from PySpark, and MinIO S3 sensor synchronization delays.
- Unnecessary distributed complexity for Cambodia's daily retail e-commerce scale (~35,000 observations/day).

### Architectural Solution
- Replaced Iceberg REST + PySpark with native **PostgreSQL 16** and pure **pandas/dbt** transformations.
- Introduced a Python-managed **canonical item identity layer** (`silver.canonical_items`, `silver.item_match_log` via `pipeline/item_matcher.py` RapidFuzz) consumed by **dbt incremental Silver models** (`items_normalized`, `item_master`, `fct_daily_prices`).
- Gold index math moved to **dbt models** (`base_prices`, `fct_daily_price_stats`, `cpi_category_daily`, `cpi_headline_daily`) + the Python **`GEKSCalculator`** (`pipeline/geks_calculator.py`, 13-period rolling GEKS-Törnqvist).
- Orchestration rebuilt as a DAG fan-out: `cpi_master_dag` → 18 `scrape_{source}_dag` → `silver_dag` → `gold_dag`; FastAPI layer removed.
- Legacy stored procedures (`gold.sp_calculate_daily_cpi`) and `silver.daily_prices` remain for the serving views (`gold.v_*`) and Metabase.
- All unit tests pass in seconds without JVM startup overhead.

---

## 2. Historical Repair Log (Legacy Iceberg Reference)

- **Phase 1 (Catalog Triage)**: Upgraded Iceberg REST image to `1.6.0` to resolve namespace view route errors.
- **Phase 2 (Schema Contract)**: Aligned table columns across `daily_prices`, `products`, `store_products`, `coicop_override`, `coicop_category_map`, `classification_queue`.
- **Phase 3 (COICOP Classifier Traps)**: Verified keyword regex and trap exceptions (Cooking Wine $\rightarrow$ 01, Slipper $\rightarrow$ 03, Wash & Wax $\rightarrow$ 07, etc.).
- **Phase 4 (Zero-Product Guards)**: Established strict guards rejecting empty scrapes before database writes.

---

## 3. COICOP Classification Repair (2026-08-19)

### Problem
- `int_coicop_classified` over-mapped products into **01 (Food)** because the generic `silver.coicop_category_map` ran **before** the keyword ladder — aeon `Grocery` (5,444 rows) and delishop generic categories swallowed phones, toys, towels, shampoo, perfume.
- Trap `~* 'ham'` (unanchored) matched inside `shAMpoo` → 01; other short substrings leaked (`gin`, `rum`, `ale`, `port`, `toy` → `TOYOTA`, `lot`, `land`, `nut`, `table`).
- Cosmetic items (sheet/face/eye/hair masks, body scrubs, shower/bath foams) fell through the personal-care guard and landed in 01/03/06.

### Fixes (`dbt/models/silver/intermediate/int_coicop_classified.sql`)
1. **Resolution order**: `override → gemini_ai → trap → keyword_ladder → category_map → store_default → UNCLASSIFIED` (keyword ladder moved **before** category_map).
2. **Personal-care guard** = first trap rule (returns `null` → routes to keyword ladder / 12) for shampoo, soap, lotion, serum, masks, scrubs, foams, etc.
3. **Medical/protective mask trap → 06** (PROTECTING/PROTECTIVE/SURGICAL/MEDICAL MASK, EARLOOP, KF../KN95/N95/FFP2/3, MELT-BLOWN) checked before the cosmetic guard.
4. **kw12 (personal care) checked first** in the keyword CASE (before 02/03/...); added mask/scrub/foam vocabulary to both the guard and kw12.
5. **Word boundaries** (`\mham\M`, `\mgin\M`, `\male\M`, `\mtables?\M`, `\mtoy(s)?\M`, ...) on short trap/kw words; removed `nut` from kw05.
6. **kw05 household before kw03 clothing** (fixes `COTTON BATH TOWEL` → 05); cup-food guard (`\mcup\M` + noodle/soup/yogurt/... → 01) so `CUP NOODLES` stays Food.
7. **Confidence swap**: keyword_ladder 0.900→**0.950**, category_map 0.950→**0.900** (name-based rules trusted over coarse store categories).

### Verification
- ABANIA PURE ARGAN SHAMPOO → **12** (keyword_ladder); phones → 08 (42), toys → 09 (89), towels → 05 (105).
- Masks/scrubs/foams: 226 → **12**, protective masks → **06**, zero leakage into 01/03.
- `silver.fct_daily_prices` full-refreshed: 45,646 rows, all 12 divisions, zero UNCLASSIFIED/REVIEW.
- Method distribution: keyword_ladder 23,478 · category_map 14,010 · exception 8,104 · override 54.
- `dbt test`: **31/31 PASS** (2026-08-19) after materializing `dim_stores` and `fct_daily_prices_imputed` (both were missing; their tests had been erroring on non-existent relations).
