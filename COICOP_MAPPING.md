# COICOP Mapping Reference — Division ↔ Store ↔ Rules

**Status:** Live mapping implemented in PostgreSQL 16 + dbt  
**Date:** 2026-08-17  
**Scope:** Maps every observation to a COICOP **division** (`01`..`12`, `UNCLASSIFIED`, or `REVIEW`).

Every silver fact row in `silver.fct_daily_prices` carries `coicop_division` + `coicop_method` + `coicop_confidence`. The mapping is computed by the dbt model `dbt/models/silver/int_coicop_classified.sql` against the **cleaned** product title (`name_clean`), ensuring promo text never pollutes keyword matching.

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

## 2. Store-Level Defaults (`int_coicop_classified.sql`)

Single-category stores receive a **fixed prior** (`store_default`, confidence 0.800) applied after the keyword ladder and category map, before the `UNCLASSIFIED` fallback:

| Stores (`store_slug`) | Default Division | Reason |
| --------------------------------------------- | ---------------------------- | --------------------------------------- |
| pharmacy, u-care, ucare, communitypharma | **06** Health | Medicines & health products |
| tela, ptt, caltex, total, new_gasoline | **07** Transport | Fuel & transport services |
| redbus | **07** Transport | Passenger bus services |
| cellcard, cellcard_wifi, smart, smart_wifi | **08** Communication | Telecom operators & ISP |
| samnangshop, arystore | **08** Communication | Phone/electronics retail |
| sokhahotel, hyyathotel, bayonbkk | **11** Restaurants & hotels | Hospitality & dining |
| aeon3 | **03** Clothing & footwear | Fashion department store |
| khmer24, realestate | **04** Housing | Rental listings |
| l192 | **05** Household | General marketplace |
| aeon, delishop | **01** Food | Grocery / supermarket |

> `store_default` is only reached when nothing higher matched; in practice every row resolves earlier (keyword_ladder, category_map, or a trap), so the defaults act as a safety net.

---

## 3. Classification Ladder (`int_coicop_classified.sql`)

Observations are resolved in order (first match wins):

```
1. override       → ref('coicop_override') seed (product_key / barcode / name match)
2. gemini_ai      → silver.dim_coicop_ai_cache (cached classifications from Gemini)
3. exceptions     → deterministic trap regex (COOKING WINE→01, TVHC SLIPPER→03, ...)
4. keyword ladder → ordered word-regex per division (order: 12, 02, 05, 03, 06,
                    09, 07, 08, 11, 10, 04, then 01)
5. category_map   → silver.coicop_category_map (store native category → division)
6. store_default  → fixed prior per store_slug (pharmacy→06, fuel→07)
7. UNCLASSIFIED   → fallback; routed to silver.classification_queue for Gemini triage
```

The keyword ladder runs **before** the generic `category_map` because store-native
categories are often too broad (aeon `Grocery` and many delishop categories map to 01).
Keyword wins over the store category so phones (08), toys (09), towels (05) and personal
care (12) are never swallowed into Food. Within the ladder, the **12 (personal care /
hygiene)** rule is checked first so beauty names containing food/material-looking words
(`honey`, `butter`, `biotin`, `silk`, `cotton`, `ale`, `gin`, `port`, ...) stay in 12.
A personal-care guard at the top of the trap case has the same effect for the trap rules.
Short alcohol/material words are word-boundaried (`\mham\M`, `\mgin\M`, `\male\M`, `\mport\M`,
`\mtables?\M`, ...) so substrings inside unrelated words (`shAMpoo`, `ARginine`, `AMINORUM`,
`MELALEUCA`, `INFLATABLE`, `LOTTE`) cannot trigger false positives.

`coicop_method` records the winning step (`override` / `gemini_ai` / `exception` / `keyword_ladder` / `category_map` / `store_default`); `coicop_confidence` ranges from 1.00 (override) down to 0.80 (store_default). The keyword ladder is trusted **above** the generic category map (0.950 vs 0.900) because store-native categories are often too coarse.

---

## 4. Product Traps (deterministic exceptions)

High-priority overrides for multilingual brand codes and multi-meaning keywords (enforced by `dbt/tests/test_traps.sql`):

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

Cosmetic & hygiene guards (added 2026-08-19):

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
| `silver.fct_daily_prices.coicop_division` | Per-observation division (`01`..`12` / `UNCLASSIFIED` / `REVIEW`) |
| `silver.fct_daily_prices.coicop_method` | Ladder classification method |
| `silver.dim_items.coicop_division` | Canonical item division |
| `silver.dim_coicop_ai_cache` | Memoization cache for Gemini AI classifications |
| `silver.classification_queue` | Operational queue for unclassified products / human triage |
| `silver.coicop_override` (seed) | Human/manual overrides (highest priority in ladder) |
| `silver.coicop_category_map` | Store native category → division mapping |
| `gold.category_weights` (seed) | Official 12-division aggregation weights (sum = 100.000%) |

---

## 6. Review & Triage App

Pending review rows in `silver.classification_queue` / `silver.needs_review` can be resolved via the dedicated Streamlit labeling interface:

```bash
streamlit run apps/labeling_app.py
```

Applying a triage decision writes to `silver.coicop_override` (or the category map) and marks the queue row as `RESOLVED`.