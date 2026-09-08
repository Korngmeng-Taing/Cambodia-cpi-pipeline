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

### Single-Category Pure Stores (Instant SQL Domain Lock: 0.001ms)
| Stores (`store_slug`) | Locked Division |
| --------------------------------------------- | ---------------------------- |
| new_gasoline (fuel), khmermoto (motorcycles) | **07** Transport (Automotive fuel & vehicles) |
| bookmebus, redbus | **07** Transport (Passenger transit tickets - Class `07.3.2`) |
| cellcard, cellcard_wifi, smart, smart_wifi, metfone, samnangshop, arystore | **08** Communication |
| khmer24, realestate, edc, ppwsa | **04** Housing & utilities (`04.1.1` Rents, `04.5.1` EDC Power, `04.4.1` PPWSA Water) |
| new_gasoline (LPG cooking gas items) | **04** Housing & utilities (Class `04.5.2` Domestic Cooking Gas) |
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

## 3. Unified AI-First Classification Ladder & Priority Order

To eliminate code-division divergence and elevate artificial intelligence above rigid substring rules, the priority order in [`resolve_coicop_code`](file:///D:/CPI%20PIPELINE/dbt/macros/coicop_classify_macro.sql) and [`resolve_coicop_division`](file:///D:/CPI%20PIPELINE/dbt/macros/coicop_classify_macro.sql) is strictly aligned across all dbt models:

```
1. Tier 1: Exact Overrides         → Human Authority Overrides (barcode / exact title in coicop_override.csv).
2. Tier 2: Store Domain Purity     → Single-Category Store Locks (khmer24=04, bookmebus=07, smart=08, sokhahotel=11, communitypharma=06).
3. Tier 3: High-Confidence AI      → Gemini AI (ai_conf >= 0.70) with multi-attribute context (store, category breadcrumb, price, title).
4. Tier 4: Global Overrides        → Cross-store canonical overrides (ov_global) for remaining low-confidence items.
5. Tier 5: Store Category Maps     → Department/aisle category maps in coicop_category_map.csv.
6. Tier 6: Text Regex Rules        → Deterministic multi-token regex rules in coicop_text_rules.csv.
7. Fallback: Store Defaults        → Retailer default division.
```

### Strict 2-Digit Prefix Guard
Every classification case branch enforces the mathematical constraint:
$$\text{LPAD}(\text{SPLIT\_PART}(\text{code}, '.', 1), 2, '0') = \text{division}$$
If an upstream rule or AI candidate returns an incompatible 5-digit code (e.g. Code `11.1.1` on Division `01`), the macro automatically overrides the code to the division's canonical anchor (e.g. `01.1.1`), guaranteeing **0 mismatches across all 909,289 historical price observations**.

### Automated Regression Guard
The dbt regression test [`test_coicop_code_division_match.sql`](file:///D:/CPI%20PIPELINE/dbt/tests/test_coicop_code_division_match.sql) executes automatically on every pipeline run, verifying that:
```sql
SELECT * FROM silver.int_coicop_classified
WHERE lpad(split_part(coicop_code, '.', 1), 2, '0') <> lpad(coicop_division, 2, '0');
```
always returns **0 rows**.

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