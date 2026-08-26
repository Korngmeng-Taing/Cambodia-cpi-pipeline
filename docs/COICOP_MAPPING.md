# COICOP Mapping Reference — Division ↔ Store ↔ Rules

**Status:** Live mapping implemented in PostgreSQL 16 + Vector Embeddings + dbt  
**Scope:** Maps every observation to a COICOP **division** (`01`..`12`, `UNCLASSIFIED`, or `REVIEW`).

Every silver fact row in `silver.clean_store_prices` carries `coicop_division` + `coicop_code` + `coicop_method` + `coicop_confidence`. The mapping is computed by the hybrid vector embedding classifier and dbt models (`int_coicop_classified.sql`) against the **cleaned** product title (`name_clean`), ensuring promo text never pollutes matching.

---

## 1. The 12 Divisions

| Code | Division | Official NIS Weight (seed) | CPI Aggregate Coverage |
| ---- | ------------------------------------------------------------------ | ------------------- | ---------------------- |
| 01 | Food and non-alcoholic beverages | 44.800% | Headline CPI (Excluded from Core CPI) |
| 02 | Alcoholic beverages, tobacco and narcotics | 1.500% | Headline & Core CPI |
| 03 | Clothing and footwear | 2.900% | Headline & Core CPI |
| 04 | Housing, water, electricity, gas and other fuels | 17.100% | Headline & Core CPI |
| 05 | Furnishings, household equipment and routine household maintenance | 3.300% | Headline & Core CPI |
| 06 | Health | 5.600% | Headline & Core CPI |
| 07 | Transport | 12.200% | Headline & Core (Fuel excluded from Core) |
| 08 | Communication (Hardware & Services) | 3.900% | Headline & Core (Hedonically Adjusted) |
| 09 | Recreation and culture | 1.900% | Headline & Core (Hedonically Adjusted) |
| 10 | Education | 1.500% | Headline & Core CPI |
| 11 | Restaurants and hotels | 3.100% | Headline & Core CPI |
| 12 | Miscellaneous goods and services (Personal Care) | 2.200% | Headline & Core CPI |
| UNCLASSIFIED | No rule matched (triage queue) | — | Excluded from Index until classified |

> Weights source: `dbt/seeds/category_weights.csv` (materialized to `gold.category_weights`), summing to 100.000%.
> **Core Inflation:** In alignment with NIS Cambodia and National Bank of Cambodia standards, Core CPI excludes volatile Division 01 (Food) and retail automotive fuels within Division 07.

---

## 2. Store-Level Categorization: Pure vs. Multi-Category Stores

### 15 Single-Category Pure Stores (Instant SQL Domain Lock: 0.001ms)
| Stores (`store_slug`) | Locked Division |
| --------------------------------------------- | ---------------------------- |
| new_gasoline | **07** Transport (Automotive fuel) |
| bookmebus, redbus | **07** Transport (Transit tickets) |
| cellcard, cellcard_wifi, smart, smart_wifi, samnangshop, arystore | **08** Communication |
| khmer24, realestate | **04** Housing & utilities |
| sokhahotel, hyyathotel, bayonbkk | **11** Restaurants & hotels |

### 5 Multi-Category Stores (Resolved via 768-dim Vector Embeddings + LLM)
| Stores (`store_slug`) | Catalog Range | Categorization Method |
| --------------------- | ------------- | --------------------- |
| **communitypharma** | Split across **06 Health** (Medicines, Panadol, Balms) and **12 Personal Care** (Cetaphil, Shampoos, Sunscreen, Soaps) | 768-dim Vector Cosine Similarity |
| **aeon & aeon3** | Hypermarket spanning **01 Food**, **02 Alcohol**, **03 Apparel**, **05 Furnishings/Towels**, **06 OTC Health**, **09 Electronics/Toys**, **12 Personal Care** | 768-dim Vector Cosine Similarity |
| **delishop** | Spans **01 Food & Groceries**, **02 Wine & Liquor**, **12 Toiletries** | 768-dim Vector Cosine Similarity |
| **l192** | Spans **03 Clothing**, **05 Kitchenware/Cookware**, **12 Bags/Cosmetics** | 768-dim Vector Cosine Similarity |

---

## 3. Classification Ladder (`pipeline/hybrid_embeddings_classifier.py`)

Observations are resolved in order (first match wins):

```
1. Tier 1: ov_exact      → Human Authority Overrides (coicop_override.csv + silver.coicop_override_manual).
2. Tier 2: store_purity  → 15 Pure Store Domain Locks (Gas->07, Telecom->08, Housing->04, Hotels->11) in 0.001ms.
3. Tier 3: vector_cosine → 768-dim Vector Cosine Similarity against 12 UN COICOP Reference Vectors.
4. Tier 4: gemini_llm    → 3-Key Load-Balanced Gemini Pro/Flash LLM Fallback (cached permanently in silver.dim_coicop_ai_cache).
```

`coicop_method` records the winning tier:
- `override` (1.000 confidence) — exact manual/seed barcode or name rules
- `store_purity` (1.000 confidence) — pure single-category store domain lock
- `vector_embedding` (0.750–1.000 confidence) — dense vector cosine match
- `gemini_llm` (0.800–1.000 confidence) — contextual LLM classification
- `fallback_default` (0.500 confidence) — rule fallback

---

## 4. Product Traps (Deterministic Exceptions)

High-priority overrides for multilingual brand codes and multi-meaning keywords:
- `BALLANTINE'S` / `CHIVAS` / `JOHNNIE WALKER` / `MARTELL` / `HENNESSY` / `SAPPORO` / `HOEGAARDEN` $\rightarrow$ **02** (Alcohol & Spirits)
- `ROHTO EYE DROPS` / `TIGER BALM` / `PANADOL` / `NAGA BALM` $\rightarrow$ **06** (Health & Medicines)
- `BIO-OIL` / `CETAPHIL` / `HEAD & SHOULDERS` / `BIORE UV` / `COLGATE` $\rightarrow$ **12** (Personal Care / Skincare)
- `BEEF TENDERLOIN` / `JASMINE RICE` / `FRESH SALMON` / `INDOMIE` $\rightarrow$ **01** (Food)