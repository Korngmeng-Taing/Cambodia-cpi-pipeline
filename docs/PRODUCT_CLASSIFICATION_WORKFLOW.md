# End-to-End Product Classification & Ingestion Architecture

> **[!NOTE]**
> **Current Pipeline Architecture:** Fully operational end-to-end — Bronze ingestion $\to$ Silver Vector Item Matching with Spec Guards $\to$ 12-Division COICOP Hybrid Classification $\to$ Gold Star Schema. Backfilled from August 18 onwards.

This document provides a comprehensive, step-by-step specification of how raw product data is scraped, cleaned, deduplicated, classified into the **United Nations COICOP (Classification of Individual Consumption According to Purpose)** hierarchy, and aggregated into the official **Cambodia Consumer Price Index (CPI)**.

---

## 1. Architectural Overview & Philosophy

The Cambodia CPI Pipeline follows a **hybrid vector & Gemini AI classification architecture**:

```mermaid
flowchart TD
    subgraph S1["Stage 1: Ingestion (Bronze)"]
        A["20 Source Scrapers\n(Supermarket, Fashion, Fuel, Telecom, etc.)"] --> B[("bronze.raw_prices\nRaw HTML / JSON / Strings")]
    end

    subgraph S2["Stage 2: Cleaning & Normalization (Silver Staging)"]
        B --> C["int_prices_cleaned.sql & text_clean.py"]
        C --> C1["• HTML decoding & promo word stripping\n• Khmer numeral & term translation\n• FX conversion to KHR via MEF\n• Package size & base unit parsing"]
    end

    subgraph S3["Stage 3: Canonical Item Matching (item_matcher.py & vector_item_matcher.py)"]
        C1 --> D{"Item Deduplication Ladder"}
        D -- "1. Barcode / SKU" --> E["Exact Match (Conf = 1.0)"]
        D -- "2. Vector Cosine (>= 0.88)" --> F["Vector Match (with Spec Guards)"]
        D -- "3. Borderline (0.75-0.88)" --> F1["🤖 Gemini Pro/Flash AI Arbitrator"]
        D -- "4. No Match (< 0.75)" --> G["Create Canonical Item (Auto)\n(silver.canonical_items)"]
    end

    subgraph S4["Stage 4: Local-First AI COICOP Classification Ladder (pipeline/hybrid_embeddings_classifier.py)"]
        G --> H{"Classification Ladder\n(First Match Wins)"}
        H -- "Tier 1" --> I["Store Purity Locks\n(Fuel, Telco, Housing, Hotels, Pharma)"]
        H -- "Tier 2" --> I2["Semantic Reference Space\n(Vector Cosine Similarity >= 0.85)"]
        H -- "Tier 3" --> M["🤖 Hierarchical Local AI (Ollama)\nClassifier Proposal $\to$ Judge Audit\n(Trained on COICOP Handbook)"]
        H -- "Tier 4" --> M1["🤖 Cloud Arbitration (Gemini Pro)\nResolution for conflicts/low-conf"]
        H -- "Tier 5" --> N["Human Review Triage\n(Silver.needs_review queue)"]
    end


    subgraph S7["Stage 5: Gold Layer Star Schema"]
        E & F & F1 & I & I2 & M & J & K & L & N --> T[("silver.clean_store_prices")]
        T --> U[("gold.dim_items & gold.dim_stores")]
        T --> V[("gold.fct_daily_prices")]
    end
```

### Core Design Principles
1. **Multi-Key Load Balancing**: Rotates 3+ Gemini API keys in thread-safe round-robin sequence to achieve $4,500$ daily requests, $45$ RPM, and automatic 429 failover.
2. **Sub-Millisecond Vector Lookup**: 95%+ of daily observations match existing canonical identities or pure store locks in $<0.1\text{ms}$.
3. **Deterministic Spec Guards**: Hardware RAM/storage, pack size multipliers, and volume discrepancies ($>10\%$) are rejected before merging to guarantee price index integrity.
4. **Zero Recurring AI Cost**: Once classified, products inherit canonical identities and are cached permanently in PostgreSQL (`silver.dim_coicop_ai_cache`).
5. **Accurate Retailer Separation**:
   - **Community Pharmacy:** Correctly separates *Panadol/Medicines* $\to$ `06 Health` from *Cetaphil/Skincare/Shampoos* $\to$ `12 Personal Care`.
   - **AEON 1 & 3:** Flexibly categorizes hypermarket listings across all 12 UN divisions (Food `01`, Alcohol `02`, Clothing `03`, Towels `05`, Headphones `09`, Personal Care `12`).

---

## 2. Stage 1: Bronze Ingestion

### Implementation Files:
- [`pipeline/bronze_scraper.py`](file:///D:/CPI%20PIPELINE/pipeline/bronze_scraper.py)
- [`scrapers/sources/`](file:///D:/CPI%20PIPELINE/scrapers/sources/)
- Database Table: `bronze.raw_prices`

### Process:
1. **Multi-Source Fetching**: 25 active scrapers run daily covering retail supermarkets (`aeon`, `delishop`), fashion marketplaces (`aeon3`), e-commerce (`l192`), Grab outlets (`grab_lucky`, `grab_chipmong`, `grab_ucare`), pharmacies (`communitypharma`), electronics (`samnangshop`, `arystore`), vehicles (`khmermoto`), telecoms (`cellcard`, `smart`, `metfone`), utilities (`edc` electricity, `ppwsa` water), real estate (`khmer24`, `realestate`), intercity transit (`redbus`, `bookmebus`), restaurants (`bayonbkk`), hospitality (`sokhahotel`, `hyyathotel`), petroleum stations (`new_gasoline`), and official exchange rates (`mef_fx`).
2. **Raw Storage & Deduplication**: Observations are stored into `bronze.raw_prices` with JSONB payloads. The table enforces deduplication via:
   ```sql
   CREATE UNIQUE INDEX uq_raw_prices_observation 
   ON bronze.raw_prices (store, source, COALESCE(url, ''), COALESCE(description, ''), scrape_date);
   ```
   `price` is excluded from the unique constraint so that retry scrapes update the existing observation rather than inserting duplicate records on the same day.

---

## 3. Stage 2: Data Cleaning & Normalization

### Implementation Files:
- [`dbt/models/silver/intermediate/int_prices_cleaned.sql`](file:///D:/CPI%20PIPELINE/dbt/models/silver/intermediate/int_prices_cleaned.sql)
- [`pipeline/text_clean.py`](file:///D:/CPI%20PIPELINE/pipeline/text_clean.py)

### Cleaning Steps:
1. **Promo Buzzword & Noise Stripping**: Strips marketing keywords (`SALE`, `PROMO`, `DISCOUNT`, `CLEARANCE`, `HOT DEAL`, `BUNDLE`).
2. **Price & Currency Removal from Title**: Strips embedded price tokens (e.g. `$10.50`, `15,000 KHR`).
3. **HTML & Symbol Cleanup**: Decodes entities (`&amp;` $\to$ `&`) and collapses whitespace.
4. **Khmer Numeral Normalization**: Converts Khmer digits `០..៩` $\to$ `0..9`.
5. **MEF FX Conversion**: Normalizes USD prices to KHR using the official daily rate from `staging.exchange_rates`.

---

## 4. Stage 3: Hybrid Vector Item Matching & Spec Guards

### Implementation Files:
- [`pipeline/vector_item_matcher.py`](file:///D:/CPI%20PIPELINE/pipeline/vector_item_matcher.py)
- [`pipeline/item_matcher.py`](file:///D:/CPI%20PIPELINE/pipeline/item_matcher.py)

```
Candidate Scraped Title
         │
         ▼
[ Step 1: Barcode / SKU Exact Match ] ──► Found? ──► APPROVE_MATCH (1.00)
         │ No
         ▼
[ Step 2: Spec Guard Compatibility Check ]
  • Storage match (128GB == 128GB)
  • Pack size match (Single == Single, 6-pack == 6-pack)
  • Volume within 10% tolerance (330ml == 330ml)
         │ Passed
         ▼
[ Step 3: Vector Cosine Similarity (text-embedding-004) ]
  • Sim >= 0.88 ──────────────────────────────────────► APPROVE_MATCH
  • 0.75 <= Sim < 0.88 ──► [ Gemini Pro AI Review ] ──► APPROVE or SPLIT
  • Sim < 0.75 ────────────────────────────────────────► SPLIT_NEW (silver.canonical_items)
```

> [!TIP]
> **Catalog Cache Safety**: The vector matcher caches pre-computed target embeddings on the instance. It validates `id(catalog)` and `len(catalog)` on every match call, completely eliminating cross-catalog memory leaks or stale vector indexing across distinct retail stores.

---

## 5. Stage 4: Local-First AI COICOP Semantic Classification

### Implementation Files:
- [`pipeline/hybrid_embeddings_classifier.py`](file:///D:/CPI%20PIPELINE/pipeline/hybrid_embeddings_classifier.py)
- [`pipeline/ollama_client.py`](file:///D:/CPI%20PIPELINE/pipeline/ollama_client.py)
- [`pipeline/key_pool.py`](file:///D:/CPI%20PIPELINE/pipeline/key_pool.py)

```
New Canonical Item
         │
         ▼
[ Tier 1: Store Purity Locks ]
  • Immediate lock for domain-pure stores (e.g. Telco -> 08, Pharma -> 06)
         │ Multi-Category Store (aeon, delishop, grab_*, l192)
         ▼
[ Tier 2: Semantic Reference Space ]
  • Vector similarity against COICOP handbook definitions (Cosine >= 0.85)
         │ Low similarity
         ▼
[ Tier 3: Hierarchical Local AI (Ollama) ]
  • Classifier: Proposes code and justification based on product name and context.
  • Judge: Audits the proposal against COICOP rules.
  • Result: Auto-classify if Judge approves with high confidence (>= 0.8).
         │ Conflict or Low Confidence
         ▼
[ Tier 4: Cloud Arbitration (Gemini Pro) ]
  • Acts as the final tie-breaker to resolve ambiguities between Local AI and data.
         │ Unresolved
         ▼
[ Tier 5: Human Review Triage ]
  • Item enters the review queue for analyst manual override.
```

---

## 6. Stage 5: Gold Star Schema

- `gold.dim_items`: Canonical items master dimension.
- `gold.dim_stores`: Retailer dimension.
- `gold.fct_daily_prices`: Conformed daily price fact table at grain `(scrape_date, store_slug, item_id)` with KHR unit prices, promo indicators, and COICOP attribution.

---

## 7. Stage 6: Economic CPI Calculation Engine (`pipeline/cpi_calculator.py`)

- **Jevons Micro-Index (`gold.fct_elementary_indices`)**:
  Calculates unweighted geometric mean price relatives for all canonical products with base period $t_0$ (August 18, 2026 = 100.00):
  $$I_{j}^{t/0} = \exp\left(\frac{1}{n_t} \sum_{i=1}^{n_t} \ln P_{i,t} - \frac{1}{n_0} \sum_{i=1}^{n_0} \ln P_{i,0}\right) \times 100.0$$
- **7-Day Compounded Class-Mean Geometric Imputation**:
  Mitigates temporary retail stockouts by updating the last observed price using the compounded daily class movement over elapsed gap days $\Delta t$:
  $$\widehat{P}_{i, t} = P_{i, t - \Delta t} \times \left(R_{c, t}\right)^{\Delta t} \quad \text{for } 1 \le \Delta t \le 7$$
  where $R_{c, t}$ is the daily geometric mean price relative of observed items in the same COICOP class. Beyond 7 consecutive missing days, items are treated as structural exits.
- **Hedonic Quality Adjustment Bridge**:
  Directly applies constant-utility adjusted prices from `silver.hedonic_adjusted_prices` for consumer electronics. When regression specifications lack variance or display severe multicollinearity, the engine gracefully skips adjustment with `SKIPPED_RANK_DEFICIENT` and falls back to observed prices.
- **Laspeyres 12-Division Macro Aggregation (`gold.fct_cpi_daily`)**:
  Combines division indices with official NIS Cambodia expenditure weights into national Headline and Core CPI.
