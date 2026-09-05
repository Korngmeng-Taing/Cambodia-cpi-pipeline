# Cambodia Daily Consumer Price Index (CPI) — Architecture & Layer Diagrams

This document contains the complete set of architecture diagrams for the Cambodia Daily CPI Medallion Pipeline across the **Bronze**, **Silver**, and **Gold** layers.

---

## 🌐 1. High-Level End-to-End Pipeline Overview

This macro-level diagram illustrates the full data journey from 20 external Cambodian retail sources through the Medallion architecture to executive dashboards and daily ML-assisted inflation nowcasting.

```mermaid
flowchart LR
    subgraph S0["23 SOURCES"]
        A1["Supermarkets & Malls\n(AEON 1 & 3, Delishop, Lucky, Chip Mong, L192)"]
        A2["Pharmacies & Tech\n(Community Pharma, Ucare, Samnang, Ary)"]
        A3["Telecom & Utilities\n(Cellcard, Smart, Fuel, Housing)"]
        A4["Transit & Hotels\n(redBus, Sokha, MEF FX)"]
    end

    subgraph S1["BRONZE LAYER (Raw)"]
        B1[("bronze.raw_prices\nImmutable Raw JSON & Tables")]
        B2[("staging.raw_scrapes\nBatch Health & Validation Logs")]
    end

    subgraph S2["SILVER LAYER (Clean & Resolve)"]
        C1["Data Hygiene & MEF FX to KHR"]
        C2["Vector Item Matcher + Spec Guards"]
        C3["4-Tier 12-Division COICOP AI Ladder"]
        C4[("silver.clean_store_prices\nCanonical Daily Observations")]
    end

    subgraph S3["GOLD LAYER (Star Schema & Index)"]
        D1[("gold.dim_items & gold.dim_stores")]
        D2[("gold.fct_daily_prices")]
        D3["Jevons Geometric Mean & Imputation"]
        D4[("gold.fct_cpi_daily & gold.fct_cpi_monthly\n12-Division & National CPI")]
    end

    subgraph S4["SERVING & ANALYTICS"]
        E1["Metabase v0.49\n(3 Streamlined Dashboards:\nMacro, Ops, Quality)"]
        E2["Power BI DirectQuery\n(Executive Inflation Dashboards)"]
        E3["ML Nowcasting Engine\n(Daily Inflation Nowcasting & NIS Chain-Linking)"]
    end

    S0 --> S1
    S1 --> S2
    S2 --> S3
    S3 --> S4

    classDef src fill:#f8f9fa,stroke:#adb5bd,stroke-width:2px,color:#212529;
    classDef brz fill:#e3f2fd,stroke:#1e88e5,stroke-width:2px,color:#0d47a1;
    classDef slv fill:#e8f5e9,stroke:#43a047,stroke-width:2px,color:#1b5e20;
    classDef gld fill:#fff8e1,stroke:#fbc02d,stroke-width:2px,color:#f57f17;
    classDef srv fill:#f3e5f5,stroke:#8e24aa,stroke-width:2px,color:#4a148c;

    class A1,A2,A3,A4 src;
    class B1,B2 brz;
    class C1,C2,C3,C4 slv;
    class D1,D2,D3,D4 gld;
    class E1,E2,E3 srv;
```

---

## 🥉 2. Bronze Layer Detail (Raw Ingestion & Circuit Breakers)

The Bronze layer ingests unstructured and semi-structured payloads across 20 stores daily, applying strict schema enforcement, zero-count circuit breakers, and raw PostgreSQL persistence.

```mermaid
flowchart TD
    subgraph ScraperRegistry["20 Scraper Engines (scrapers/sources/)"]
        direction TB
        S_REST["REST & JSON Proxies\n• AEON 1 & 3 Next.js Proxy\n• Delishop API v2\n• Samnang & Ary WooCommerce"]
        S_GQL["GraphQL & Supabase\n• L192 GraphQL Engine\n• Community Pharmacy PostgREST\n• MOC Gasoline GraphQL"]
        S_HTML["DOM & Multi-URL Crawlers\n• Cellcard & Smart DOM\n• Khmer24 & Realestate.com.kh\n• Bayon Restaurant Apollo State"]
        S_API["Official Transit & Macro APIs\n• redBus & BookMeBus APIs\n• Sokha & Hyatt Booking Engines\n• MEF Official Daily FX API"]
    end

    subgraph Validation["Bronze Validation & Circuit Breaker (pipeline/canonical.py)"]
        V1{"Zero-Count Circuit Breaker\n(Rows > 0?)"}
        V2["Schema v1.0 Normalizer\n(Float prices, timestamps, JSON payload)"]
        V3["Daily Dedup Guard\nuq_raw_prices_observation"]
    end

    subgraph BronzeStorage["PostgreSQL Bronze Storage (sql/schema.sql)"]
        T1[("bronze.raw_prices\n• raw_price_id (PK)\n• store_id & source_name\n• item_description_raw\n• price & currency (USD/KHR)\n• raw_payload (JSONB)\n• scraped_at (Partitioned)")]
        T2[("staging.raw_scrapes\n• scrape_date & store_slug\n• record_count & status\n• batch_id (UUID)")]
        T3[("staging.exchange_rates\n• execution_date (PK)\n• rate (USD/KHR)\n• source ('official')")]
        T4[("bronze.scrape_errors\n• error_type & message\n• raw_record payload")]
    end

    ScraperRegistry --> V1
    V1 -- "Failed (0 Rows / Timeout)" --> T4
    V1 -- "Passed" --> V2
    V2 --> V3
    V3 --> T1
    V3 --> T2
    S_API -.-> T3

    classDef box fill:#e1f5fe,stroke:#0288d1,stroke-width:2px,color:#01579b;
    classDef table fill:#ffffff,stroke:#0288d1,stroke-width:2px,stroke-dasharray: 5 5,color:#01579b;
    class S_REST,S_GQL,S_HTML,S_API,V1,V2,V3 box;
    class T1,T2,T3,T4 table;
```

---

## 🥈 3. Silver Layer Detail (Vector Matching & COICOP Classification)

The Silver layer transforms noisy, multilingual raw data into standardized observations via 768-dim multilingual vector embeddings, deterministic spec guards, 3-key load balancing, and 12-division UN COICOP classification.

```mermaid
flowchart TD
    subgraph Stage1["Stage 1: Ingestion Hygiene (silver.int_prices_cleaned)"]
        A1["Raw Strings from Bronze"] --> A2["• Decode HTML & Strip Promo Buzzwords\n• Translate Khmer Numerals (០..៩ -> 0..9)\n• Convert USD -> KHR via MEF Daily Rate\n• Extract Base Units (g, kg, ml, L) & unit_price_khr"]
    end

    subgraph Stage2["Stage 2: Incremental Item Matching (pipeline/vector_item_matcher.py)"]
        A2 --> B1{"Is (store_slug, raw_sku)\nalready matched in history?"}
        B1 -- "YES (95% of daily rows)" --> B2["Instant SQL JOIN to Canonical UUID (<0.1ms)\n└──► Auto-Inherits Existing COICOP Code!"]
        B1 -- "NO (5% new rows)" --> B3{"Matching Ladder"}
        
        B3 -- "Step 1" --> B4["Exact Barcode / SKU Match (Conf = 1.0)"]
        B3 -- "Step 2" --> B5["Vector Cosine Sim (>= 0.88)\n+ Deterministic Spec Guards (RAM, Storage, Pack)"]
        B3 -- "Step 3 (0.75 <= Sim < 0.88)" --> B6["🤖 3-Key Gemini Pro/Flash AI Arbitrator\n(APPROVE_MATCH vs SPLIT_NEW)"]
        B3 -- "Step 4 (< 0.75)" --> B7["Create New Canonical UUID (silver.canonical_items)"]
    end

    subgraph Stage3["Stage 3: 12-Division COICOP Ladder (Only for New Items)"]
        B7 --> C1{"4-Tier Classification Ladder"}
        C1 -- "Tier 1" --> C2["Human Authority Overrides (coicop_override.csv)"]
        C1 -- "Tier 2" --> C3["15 Pure Store Domain Locks (Gas->07, Telecom->08)"]
        C1 -- "Tier 3" --> C4["Vector Cosine vs 12 UN COICOP Reference Spaces\n• Panadol -> 06 Health\n• Cetaphil / Shampoo -> 12 Personal Care\n• AEON Multi-Division Catalog"]
        C1 -- "Tier 4" --> C5["🤖 Gemini Pro/Flash Fallback & silver.dim_coicop_ai_cache"]
    end

    subgraph Stage4["Stage 4 & 5: Hedonics & Final Assembly"]
        C2 & C3 & C4 & C5 & B2 & B4 & B5 & B6 --> D1["Hedonic Quality Adjustment\n(Division 08 & 09 Tech Specs)"]
        D1 --> D2["Promo Clamping [0%, 95%] & Outlier Tagging\n+ Windowed Dedup on (scrape_date, store_slug, item_id)"]
        D2 --> D3[("silver.clean_store_prices\nClean Conformed Daily Facts\n(Satisfies uq_clean_store_prices_date_store_item)")]
    end

    classDef slvBox fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20;
    classDef slvTable fill:#ffffff,stroke:#2e7d32,stroke-width:2px,stroke-dasharray: 5 5,color:#1b5e20;
    class A2,B1,B2,B3,B4,B5,B6,B7,C1,C2,C3,C4,C5,D1,D2 slvBox;
    class D3 slvTable;
```

---

## 🥇 4. Gold Layer Detail (Star Schema, Two-Tier Jevons/Laspeyres Math & ML Inflation Nowcasting)

The Gold layer structures data into a Kimball dimensional star schema, applies the ILO/IMF two-tier elementary aggregation standard (subclass Jevons → division Laspeyres), 7-day ILO class-mean imputation, continuous series chain-linking splice factor, single-writer monthly CPI mart (`gold.fct_cpi_monthly`), and produces daily ML-assisted inflation nowcasts with dynamic uncertainty decay and official NIS benchmark chain-linking.

```mermaid
flowchart TD
    subgraph StarSchema["1. Kimball Star Schema Dimensional Model (gold_dag)"]
        G_DIM1[("gold.dim_items\n• item_id (PK UUID)\n• canonical_name & brand\n• coicop_division & code\n• first_seen / last_seen")]
        G_DIM2[("gold.dim_stores\n• store_slug (PK)\n• store_name & channel\n• default_coicop_division")]
        G_FACT[("gold.fct_daily_prices\n• (scrape_date, store_slug, item_id) [PK]\n• price_khr & unit_price_khr\n• discount_pct & on_promo\n• is_outlier & cpi_eligible")]
        G_CLASS[("gold.fct_coicop_class_daily\n• 4-digit subclass daily mart")]
        
        G_DIM1 --> G_FACT
        G_DIM2 --> G_FACT
    end

    subgraph IndexEngine["2. Two-Tier CPI Index Math & Econometric Engine (pipeline/cpi_calculator.py)"]
        G_FACT --> M1["Jevons Geometric Mean Elementary Micro-Index\nP_Jevons = exp( 1/N * sum( ln(P_i,t) ) )\ngold.fct_elementary_indices"]
        M1 --> M2["ILO Class-Mean 7-Day Imputation\n(Advances missing prices by observed division movement)"]
        M2 --> M3["Tier 1: 4-Digit Subclass Jevons Aggregation\nI_c = exp( 1/N_c * sum( ln(R_i) ) ) * 100.0"]
        M3 --> M4["Tier 2: Division Laspeyres Roll-Up\n(48 Official NIS Subclass Weights w_c)\nI_Div = sum(w_c * I_c) / sum(w_c)"]
        M4 --> M5["Continuous Chain-Linking & Laspeyres Headline/Core CPI\n• Splice Factor: S = avg_december_cpi / 100.0\n• gold.fct_cpi_daily & gold.fct_cpi_monthly (Single Writer)"]
        M1 --> G_CLASS
    end

    subgraph NowcastEngine["3. ML Inflation Nowcasting Engine (gold.fct_cpi_nowcast)"]
        M4 & M5 --> F1["Month-to-Date Realized Aggregation\n• Observed days mean CPI\n• Food (01) & Transport (07) 7-Day Momentum\n• Cambodian Festival Shock Calendar (KNY, Pchum Ben)"]
        F1 --> F2["Econometric Nowcasting Engine (ml/nowcaster.py)\n(NIS Base 2006 Chain-Linking)"]
        F2 --> F3["Daily MTD Inflation Nowcasts & 95% Confidence Intervals\ngold.fct_cpi_nowcast & gold.v_nowcast_evaluation"]
    end

    subgraph Serving["4. Executive BI & Operational Observability"]
        M4 & M5 --> B1["Power BI Analytics\n• Real-Time Inflation Tracking\n• Category Price Elasticity\n• Promo Impact BI"]
        StarSchema --> B2["Metabase v0.49\n• 3 Consolidated Dashboards\n• Macro CPI & Inflation Analytics\n• Operations & 23-Source Telemetry\n• Silver Data Quality Screener"]
    end

    classDef gldBox fill:#fffde7,stroke:#f57f17,stroke-width:2px,color:#e65100;
    classDef gldTable fill:#ffffff,stroke:#f57f17,stroke-width:2px,stroke-dasharray: 5 5,color:#e65100;
    class M1,M2,M3,M4,M5,F1,F2,F3,B1,B2 gldBox;
    class G_DIM1,G_DIM2,G_FACT,G_CLASS gldTable;
```
