# COICOP Mapping Reference — Division ↔ Store ↔ Rules

**Status:** Live mapping implemented in PostgreSQL 16 + dbt  
**Date:** 2026-08-17  
**Scope:** Maps every observation to a COICOP **division** (`01`..`12`, `UNCLASSIFIED`, or `REVIEW`).

Every silver fact row in `silver.clean_store_prices` carries `coicop_division` + `coicop_code` + `coicop_method` + `coicop_confidence`. The mapping is computed by the dbt model `dbt/models/silver/intermediate/int_coicop_classified.sql` against the **cleaned** product title (`name_clean`), ensuring promo text never pollutes keyword matching.

---

## 1. The 12 Divisions

| Code | Division | Official NIS Weight (seed) |
| ---- | ------------------------------------------------------------------ | ------------------- |
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
| UNCLASSIFIED | No rule matched (incl. REVIEW backlog) | — |

> Weights source: `dbt/seeds/category_weights.csv` (materialized to `gold.category_weights`), summing to 100.000%.

---

## 2. Store-Level Purity & Defaults

Single-division stores are now enforced as a **hard purity invariant** (Tier 2,
confidence 0.850, applied *before* all automatic signals — only exact/per-store
human overrides beat it):

| Stores (`store_slug`) | Forced Division |
| --------------------------------------------- | ---------------------------- |
| communitypharma | **06** Health |
| khmer24, realestate | **04** Housing |
| sokhahotel, hyyathotel, hyatt, bayonbkk | **11** Restaurants & hotels |
| bookmebus, redbus, redmebus | **07** Transport (transit) |
| new_gasoline | **07** Transport (fuel) |
| arystore, samnangshop, cellcard, cellcard_wifi, smart, smart_wifi | **08** Communication |

Guarded by `test_communitypharma_coicop_06`, `test_realestate_khmer24_coicop_04`,
`test_coicop_11_stores_only`, `test_no_aeon_in_coicop_06`,
`test_coicop_08_stores_only`, `test_no_tech_or_housing_in_coicop_12`.
Note: AEON is NOT store-pure — it legitimately stocks OTC medicine, so
`test_no_aeon_in_coicop_06` only rejects weak heuristic methods
(keyword/category guesses) landing in Health; override / gemini_ai /
exception classifications into 06 at AEON are trusted.

Remaining stores (aeon, delishop, aeon3, l192, nikashop…) are multi-division
and fall through the full ladder; `coicop_store_defaults.csv` remains as a
late safety net.

---

## 3. Classification Ladder (`int_coicop_classified.sql`)

Observations are resolved in order (first match wins). The model is **daily-scoped** (classifies only the current run's `scrape_date`; historical rows are preserved) and implements a streamlined **AI-First Classification Engine**:

```
1. ov_exact      → Barcode/product_key exact matches + store-tagged name rules
                   (seed silver.coicop_override + table silver.coicop_override_manual) — human authority.
2. store_purity  → Domain purity invariant: pharmacies→06, khmer24/realestate→04,
                   hotels→11, bookmebus/redbus/fuel→07, dedicated telecoms→08.
3. ov_global     → Untagged global name-substring override rules (e.g. COOKING WINE→01, HAIRCUT→12).
4. gemini_ai     → silver.dim_coicop_ai_cache (exact normalized-name match,
                   conf >= 0.50) pre-warmed by Gemini Flash in batches of 50.
5. category_map  → silver.coicop_category_map (store native category -> division fallback).
6. store_default → Hard store default priors + coicop_store_defaults seed.
7. UNCLASSIFIED  → Fallback queue for subsequent AI batch pre-warming.
```

`coicop_method` records the winning tier:
- `override` (1.000 confidence) — exact manual/seed barcode or name rules
- `store_purity` (0.850 confidence) — domain purity pinning (pharmacies, hotels, transit, fuel, telecoms)
- `gemini_ai` (0.500–1.000 confidence) — pre-warmed AI cache hits with confidence >= 0.50
- `gemini_ai_low_conf` (0.400 confidence) — low-confidence AI classifications requiring review
- `category_map` (0.900 confidence) — native store taxonomy mapping
- `store_default` (0.800 confidence) — generic store prior default
- `unclassified` (0.000 confidence) — unmapped items falling into the triage queue

---


## 4. Product Traps (deterministic exceptions)

High-priority overrides for multilingual brand codes and multi-meaning keywords (enforced by `dbt/tests/test_traps.sql`):

- `BALLANTINE'S` / `CHIVAS` / `JOHNNIE WALKER` / `MARTELL` / `HENNESSY` / `SAPPORO` / `HOEGAARDEN` $\rightarrow$ **02** (Alcohol & Spirits)
- `ROHTO EYE DROPS` / `TIGER BALM` / `KWAN LOONG` / `NAGA BALM` / `BOW BALM` $\rightarrow$ **06** (Health & Medicated Balms)
- `BIO-OIL` / `SAFORELLE` / `CETAPHIL` / `KLORANE` / `HADALABO` / `OLD SPICE DEODORANT` $\rightarrow$ **12** (Personal Care / Skincare)
- `BEEF SPARERIB` / `CAMPAGNA SPAGHETTI` / `BUTTER COOKIES VANILLA RING` / `CANDY NECKLACE` / `PRINGLES` $\rightarrow$ **01** (Food & Confectionery)
- `COOKING WINE 750ML` $\rightarrow$ **01** (Food)
- `SOMERSBY CIDER 4X330ML` $\rightarrow$ **02** (Alcohol)
- `WOLF BLASS SHIRAZ 750ML` $\rightarrow$ **02** (Alcohol)
- `TVHC SLIPPER UNISEX` $\rightarrow$ **03** (Clothing)
- `LIX FLOOR CLEANER 3.8L` $\rightarrow$ **05** (Furnishings / Household)
- `TV COFFEE FILTER 40` $\rightarrow$ **05** (Household equipment)
- `GREEN ONION SLICER` $\rightarrow$ **05** (Household equipment)
- `LITTLE TREES BLACK ICE` $\rightarrow$ **07** (Transport / Car care)
- `LITTLE TREES WASH&WAX` $\rightarrow$ **07** (Transport / Car care)
- `MY-RING NOTES A5` $\rightarrow$ **09** (Recreation / Stationery)
- `DOG FOOD / CAT FOOD / PET FOOD / PETS` $\rightarrow$ **09** (Recreation / UN COICOP 09.3.4 Pets and related products)
- `WAKAME MIXED RICE WITH SALMON` $\rightarrow$ **11** (Restaurant / Prepared food)
- `SPICY BEEF HOT POT 270G` $\rightarrow$ **01** (Food)
- `SUNPLAY SKIN AQUA SPF50` / `LIPICE` $\rightarrow$ **12** (Miscellaneous / Cosmetics)

Cosmetic & hygiene guards (added 2026-08-19, updated 2026-08-23):

- **Personal-care guard (first trap rule, returns `null`):** any name matching `shampoo | conditioner | body wash | lotion | perfume | soap | mask (word-boundaried \mmask\M) | sheet/face/eye/hair/foot/body mask | mask sheet/pack/box | facial mask | facemask | body/face/foot scrub | shower/bath foam | shower/bath cream | bubble bath | shower/bath oil | serum | toner | cleanser | tonic | ...` is routed to the keyword ladder so cosmetics never fall through to food/material words (`honey`, `butter`, `silk`, `sugar`, `salt`, `oil`, `rice`). Cosmetics land in **12** via the first keyword rule (kw12).
- `BODY SCRUB` / `SHOWER CREAM` / `BATH FOAM` / `SHEET MASK` / `EYE MASK` / `HAIR MASK` / `FACEMASK` / `MASK SHEET PACK` $\rightarrow$ **12** (Miscellaneous / personal care)
- **Medical / protective masks** (checked before the guard): `PROTECTING MASK` / `PROTECTIVE MASK` / `SURGICAL MASK` / `MEDICAL MASK` / `EARLOOP` / `EAR LOOP` / `KF..` / `KN95` / `N95` / `FFP2` / `FFP3` / `MELT-BLOWN` $\rightarrow$ **06** (Health)

Service traps (corrected 2026-08-19):

- `HOSPITAL` / `CLINIC` / `DOCTOR` / medical & dental visits, `EYE TEST` / `EYE EXAM`, `PRESCRIPTION` / `OPTICAL` GLASSES, `CONTACT LENS` / `LENS SOLUTION` $\rightarrow$ **06** (Health)
- `LAUNDRY` (service/wash), `DRY CLEANING`, `TAILOR` $\rightarrow$ **03** (Clothing — cleaning/repair of clothing)
- `HAIRCUT` / `HAIR SALON` / `BEAUTY SALON` / `NAIL SALON`, `SPA`, `MASSAGE` $\rightarrow$ **12** (Miscellaneous / personal care services)
- `GYM` / `FITNESS` / `YOGA CLASS` / `SWIMMING POOL`, `KARAOKE`, `BOWLING`, `CINEMA` / `MOVIE THEATER`, `THEATRE`, `CONCERT`, theme/water/amusement parks, `ZOO`, `MUSEUM`, `GALLERY`, `EXHIBITION`, `TOUR` (guide/ticket/package), `TRAVEL AGENT` $\rightarrow$ **09** (Recreation and culture)
- `VISA FEE`, `PASSPORT`, `INSURANCE` (travel/health/medical) $\rightarrow$ **12** (Miscellaneous / insurance & other services)

---

## 5. Storage Schema in PostgreSQL 16

| Table | Role |
| ------------------------------------- | --------------------------------------------------------- |
| `silver.clean_store_prices.coicop_division` | Per-observation division (`01`..`12` / `UNCLASSIFIED` / `REVIEW`) |
| `silver.clean_store_prices.coicop_method` | Ladder classification method (`gemini_ai`, `store_default`, `override`) |
| `gold.dim_items.coicop_division` | Canonical item division in conformed Gold master catalog |
| `silver.dim_coicop_ai_cache` | Memoization cache for Gemini AI classifications (AI-first tier 3; stores `model_version`) |
| `silver.classification_queue` | Automated triage tracking for unclassified products & AI sweeps |
| `silver.coicop_override` (seed) | Curated override rules — barcode and exact product overrides |
| `silver.coicop_store_defaults` (seed) | Default division mappings per retail source |
| `gold.category_weights` (seed) | Official 12-division aggregation weights (sum = 100.000%) |

---

## 6. Review & Triage App

Unclassified observations are automatically swept and classified by Gemini AI via `pipeline.gemini_coicop_classifier` and cached in `silver.dim_coicop_ai_cache`.

Applying a triage decision writes to `silver.coicop_override_manual`
(migration 010 — survives every `dbt seed`) or the category map, and marks the
queue row as `RESOLVED`.