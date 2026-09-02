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

### 5 Multi-Category Stores (Resolved via 768-dim Vector Embeddings + Gemini AI)

| Store | Categories | Resolution Method |
| :--- | :--- | :--- |
| **aeon** | Spans **01 Food**, **02 Alcohol**, **05 Cleaning**, **12 Personal Care** | 768-dim Vector Cosine Similarity |
| **aeon3** | Spans **03 Clothing & Footwear**, **05 Textiles** | 768-dim Vector Cosine Similarity |
| **delishop** | Spans **01 Food**, **02 Alcohol**, **05 Household** | 768-dim Vector Cosine Similarity |
| **communitypharma** | Split between **06 Pharmaceuticals** and **12 Personal Care / Cosmetics** | 768-dim Vector Cosine Similarity |
| **l192** | Spans **03 Clothing**, **05 Kitchenware/Cookware**, **12 Bags/Cosmetics** | 768-dim Vector Cosine Similarity |

---

## 3. Classification Ladder (`pipeline/hybrid_embeddings_classifier.py`)

Observations are resolved in order (first match wins):

```
1. Tier 1: ov_exact      → Human Authority Overrides (coicop_override.csv + silver.coicop_override_manual).
2. Tier 2: store_purity  → 15 Pure Store Domain Locks (Gas->07, Telecom->08, Housing->04, Hotels->11) in 0.001ms.
3. Tier 3: vector_cosine → 768-dim Vector Cosine Similarity against Granular 4-Digit & 12-Division Bilingual Reference Vectors (Khmer & English).
4. Tier 4: gemini_ai     → 3-Key Load-Balanced Gemini Pro/Flash AI Fallback (cached permanently in silver.dim_coicop_ai_cache).
```

`coicop_method` records the winning tier:
- `override` (1.000 confidence) — exact manual/seed barcode or name rules
- `store_purity` (1.000 confidence) — pure single-category store domain lock
- `vector_embedding` (0.750–1.000 confidence) — dense vector cosine match against 4-digit/12-division reference spaces
- `gemini_ai` (0.800–1.000 confidence) — contextual AI classification
- `fallback_default` (0.500 confidence) — rule fallback

---

## 4. Granular 4-Digit / 5-Digit COICOP Reference Taxonomy

The pipeline maps products directly into granular 4-digit / 5-digit UN COICOP 2018 classes supporting granular micro-basket aggregation in `gold.fct_coicop_class_daily`:

- **01 Food & Non-Alcoholic Beverages**:
  - `01.1.1` Bread & cereals (អង្ករ, នំប៉័ង, មី, ម្សៅ)
  - `01.1.2` Meat (សាច់គោ, សាច់ជ្រូក, សាច់មាន់, សាច់ក្រក)
  - `01.1.3` Fish & seafood (ត្រី, ត្រីសាម៉ុង, បង្គា, មឹក, ក្តាម, ប្រហុក)
  - `01.1.4` Milk, cheese & eggs (ទឹកដោះគោ, ឈីស, ប៊ឺ, ពងមាន់)
  - `01.1.5` Oils & fats (ប្រេងឆា, ប្រេងដូង, ប្រេងអូលីវ)
  - `01.1.6` Fruit (ផ្លែឈើ, ផ្លែប៉ោម, ចេក, ក្រូច, ស្វាយ)
  - `01.1.7` Vegetables (បន្លែ, ប៉េងប៉ោះ, ដំឡូងបារាំង, ខ្ទឹម, ម្ទេស)
  - `01.1.8` Sugar, jam, chocolate & confectionery (ស្ករស, ទឹកឃ្មុំ, សូកូឡា, ស្ករគ្រាប់, នំ)
  - `01.1.9` Food products n.e.c. (អំបិល, ទឹកត្រី, ទឹកស៊ីអ៊ីវ, គ្រឿងទេស)
  - `01.2.1` Coffee, tea & cocoa (កាហ្វេ, តែ, កាកាវ)
  - `01.2.2` Mineral waters, soft drinks & juices (ទឹកបរិសុទ្ធ, ទឹកក្រូច, កូកាកូឡា)
- **02 Alcoholic Beverages & Tobacco**:
  - `02.1.1` Spirits & liqueurs (ស្រា, ស្រាវីស្គី)
  - `02.1.2` Wine (ស្រាក្រហម, ស្រាស)
  - `02.1.3` Beer (ស្រាបៀរ, ស្រាបៀរអង្គរ)
  - `02.2.0` Tobacco (បារី)
- **03 Clothing & Footwear**: `03.1.2` Garments (ខោអាវ), `03.2.1` Footwear (ស្បែកជើង)
- **04 Housing & Utilities**: `04.1.1` Rentals (ផ្ទះជួល), `04.4.1` Water (ទឹកស្អាត), `04.5.1` Electricity (អគ្គិសនី), `04.5.2` Cooking Gas (ហ្គាស)
- **05 Furnishings & Cleaning**: `05.1.1` Furniture (តុ, កៅអី), `05.2.1` Textiles (ភួយ, កន្សែង), `05.6.1` Cleaning goods (សាប៊ូបោកខោអាវ, ទឹកលាងចាន)
- **06 Health**: `06.1.1` Pharmaceuticals (ថ្នាំពេទ្យ, ប៉ារ៉ាសេតាម៉ុល), `06.1.2` Medical products (បង់រុំរបួស, ប្រេងកូឡា, ម៉ាស់)
- **07 Transport**: `07.2.2` Vehicle fuels & lubricants (សាំង, ម៉ាស៊ូត), `07.3.2` Bus & coach tickets (សំបុត្រឡានក្រុង)
- **08 Communication**: `08.2.0` Phone hardware (ទូរស័ព្ទ), `08.3.0` Telecom & Internet data (ស៊ីមកាត, អ៊ីនធឺណិត)
- **09 Recreation & Culture**: `09.1.1` TV & Audio (ទូរទស្សន៍, កាស), `09.1.3` Computers & Laptops (កុំព្យូទ័រ), `09.3.1` Toys (ប្រដាប់ក្មេងលេង), `09.5.1` Books & Stationery (សៀវភៅ, ប៊ិច)
- **10 Education**: `10.1.0` Primary / secondary schooling (ការអប់រំ)
- **11 Restaurants & Hotels**: `11.1.1` Restaurants & cafes (អាហារដ្ឋាន, ហាងកាហ្វេ), `11.2.0` Hotel lodging (សណ្ឋាគារ)
- **12 Personal Care & Effects**: `12.1.1` Hair care (សាប៊ូកក់សក់), `12.1.3` Skincare & personal hygiene (សាប៊ូដុសខ្លួន, ថ្នាំដុសធ្មេញ, ឡេ), `12.3.1` Jewelry & watches (គ្រឿងអលង្ការ, នាឡិកា), `12.3.2` Bags & luggage (កាបូប)

---

## 5. Product Traps (Deterministic Exceptions)

High-priority overrides for multilingual brand codes and multi-meaning keywords:
- `BALLANTINE'S` / `CHIVAS` / `JOHNNIE WALKER` / `MARTELL` / `HENNESSY` / `SAPPORO` / `HOEGAARDEN` $\rightarrow$ **02** (Alcohol & Spirits)
- `ROHTO EYE DROPS` / `TIGER BALM` / `PANADOL` / `NAGA BALM` $\rightarrow$ **06** (Health & Medicines)
- `BIO-OIL` / `CETAPHIL` / `HEAD & SHOULDERS` / `BIORE UV` / `COLGATE` $\rightarrow$ **12** (Personal Care / Skincare)
- `BEEF TENDERLOIN` / `JASMINE RICE` / `FRESH SALMON` / `INDOMIE` $\rightarrow$ **01** (Food)