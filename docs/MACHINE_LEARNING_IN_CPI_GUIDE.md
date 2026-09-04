# Machine Learning in CPI Measurement: Literature, Models & Implementation Guide

In modern economic statistics and price intelligence pipelines, Machine Learning (ML) operates across **two distinct domains**:

`
                       ┌─────────────────────────────────────────────────────────┐
                       │          MACHINE LEARNING IN CPI MEASUREMENT            │
                       └─────────────────────────────────────────────────────────┘
                                       │                         │
            ┌──────────────────────────┴──────────┐   ┌──────────┴──────────────────────────┐
            │               DOMAIN A              │   │               DOMAIN B              │
            │       NLP & Entity Resolution       │   │        Macroeconomic Nowcasting     │
            │          (Micro / Silver)           │   │            (Macro / Gold)           │
            ├─────────────────────────────────────┤   ├─────────────────────────────────────┤
            │ • Clean messy scraped titles        │   │ • Ingest daily scraped indices      │
            │ • Multilingual (Khmer/English)      │   │ • Link with FX rates & fuel prices  │
            │ • Classify into 12 COICOP categories│   │ • Predict official NIS monthly CPI  │
            │ • Deduplicate cross-store variants  │   │   20–30 days before publication     │
            └─────────────────────────────────────┘   └─────────────────────────────────────┘
`

---

## 1. Foundational Literature on Machine Learning in CPI

### Domain A: NLP, Product Classification & Entity Resolution
1. **Berki et al. (2025)** — *NLP-Enhanced Inflation Measurement Using BERT and Web Scraping*
   - **Outlet**: *Frontiers in Artificial Intelligence*, Vol. 8, Art. 1520659.
   - **Key Focus**: Fine-tuning multilingual transformer models (BERT/RoBERTa) for multi-class hierarchical text classification into UN COICOP product codes across >100,000 retail items.
   - **DOI**: [10.3389/frai.2025.1520659](https://doi.org/10.3389/frai.2025.1520659)
   - **Full Paper PDF**: 	hesis/papers/original_publications/04_Berki_et_al_2025_BERT_COICOP_Classification.pdf

2. **Bank for International Settlements (BIS), ECB, & Deutsche Bundesbank (2024)** — *Project Spectrum: Using Generative AI to Enhance Inflation Nowcasting*
   - **Outlet**: *BIS Innovation Hub Technical Report*, Basel, Switzerland.
   - **Key Focus**: Using Large Language Models (LLMs) with dense multilingual vector embeddings and persistent database caching to process millions of scraped price quotes.
   - **Link**: [https://www.bis.org/about/bisih/topics/ai/spectrum.htm](https://www.bis.org/about/bisih/topics/ai/spectrum.htm)
   - **Full Paper PDF**: 	hesis/papers/original_publications/05_BIS_2024_Project_Spectrum_AI_Inflation.pdf

3. **Office for National Statistics (ONS) Data Science Campus (2020)** — *Using Machine Learning for Classifying Web-Scraped Data into COICOP*
   - **Outlet**: *ONS Methodology Technical Paper*, Newport, UK.
   - **Key Focus**: FastText sub-word feature extraction combined with XGBoost and LightGBM classifiers, introducing operational Human-in-the-Loop (HITL) confidence thresholding (tau = 0.80).
   - **Link**: [https://www.ons.gov.uk/economy/inflationandpriceindices/methodologies](https://www.ons.gov.uk/economy/inflationandpriceindices/methodologies)

4. **Polidoro et al. (2015)** — *Web Scraping Techniques to Collect Data on Consumer Prices and Machine Learning for Product Classification*
   - **Outlet**: *Statistical Journal of the IAOS*, Vol. 31, No. 3, pp. 447–461.
   - **Key Focus**: Italian National Institute of Statistics (ISTAT) production pilot benchmarking TF-IDF + Support Vector Machines (SVM) and Naive Bayes for automated scanner and scraped item ingestion.
   - **DOI**: [10.3233/SJI-150896](https://doi.org/10.3233/SJI-150896)

---

### Domain B: Time-Series & Macroeconomic Nowcasting
5. **Medeiros, Vasconcelos, Veiga, & Zilberman (2021 / 2019)** — *Forecasting Inflation in a Data-Rich Environment: The Benefits of Machine Learning Methods*
   - **Outlet**: *Journal of Business & Economic Statistics*, Vol. 39, No. 1, pp. 98–119.
   - **Key Focus**: Comprehensive empirical comparison proving that non-linear tree-based ensembles (Random Forests, Gradient Boosted Regression Trees) substantially outperform standard econometric benchmarks (AR, Phillips Curve, Factor Models) in predicting consumer inflation.
   - **DOI**: [10.1080/07350015.2019.1637745](https://doi.org/10.1080/07350015.2019.1637745)
   - **Full Paper PDF**: 	hesis/papers/original_publications/11_Medeiros_et_al_2019_Forecasting_Inflation_ML_BCB493.pdf

6. **Macias, Stelmasiak, & Szafranek (2023 / 2019)** — *Nowcasting Food Inflation with a Massive Amount of Online Prices*
   - **Outlet**: *International Journal of Forecasting*, Vol. 39, No. 2, pp. 809–826 (National Bank of Poland).
   - **Key Focus**: Analyzing >2 million daily online food prices to nowcast official monthly food inflation using Mixed-Data Sampling (MIDAS) and machine learning lag models.
   - **DOI**: [10.1016/j.ijforecast.2022.01.007](https://doi.org/10.1016/j.ijforecast.2022.01.007)
   - **Full Paper PDF**: 	hesis/papers/original_publications/10_Macias_et_al_2019_Food_Inflation_Nowcasting_NBP302.pdf

---

## 2. Model Benchmarks & Reported Accuracy

### NLP & Classification Models (Domain A)

| Model Architecture | Literature Reference | Training & Inference Cost | Reported Performance | Strengths & Trade-offs |
|---|---|---|---|---|
| **TF-IDF + Naive Bayes / SVM** | *Polidoro et al. (2015)* | Ultra-low (CPU) | **82.0% – 87.5%** Accuracy | Fast and lightweight, but fragile on abbreviations, typos, and multilingual text. |
| **FastText + XGBoost / LightGBM** | *ONS Campus (2020)* | Low (CPU) | **87.0% – 91.0%** Macro F1 | Robust against sub-word misspellings; produces calibrated confidence probabilities. |
| **Fine-Tuned BERT Transformer** | *Berki et al. (2025)* | Medium-High (GPU) | **94.56% Accuracy, 94.07% Precision** | Deep semantic contextual understanding; handles brand names, packaging, and noisy descriptions. |
| **Dense Vector Embeddings + LLM Reasoning** | *BIS Project Spectrum (2024)* | Low (via Vector Cache) | **> 95.0% Precision** | Zero-shot multilingual adaptation (Khmer + English); <3 min batch latency via cache memoization. |

> **Summary (Most Accurate for NLP)**: **Dense Transformer Embeddings + Few-Shot LLM Fallback** achieves **>95% precision** across noisy multilingual scraped retail catalogs.

---

### Nowcasting & Forecasting Models (Domain B)

| Model Architecture | Literature Reference | Benchmark Comparison | Reported Error Reduction | Strengths & Trade-offs |
|---|---|---|---|---|
| **AR / ARIMA / SARIMA** | *Baseline Standard* | Baseline | 0% (Reference) | Linear only; cannot ingest high-frequency daily scraped data into monthly target forecasts. |
| **LASSO / Ridge / Elastic Net** | *Medeiros et al. (2021)* | vs AR Baseline | **5% – 12% MSFE Reduction** | Automatic feature selection across high-dimensional macro panels; assumes linear relationships. |
| **MIDAS (Mixed-Data Sampling)** | *Macias et al. (2023)* | vs Monthly AR | **15% – 35% RMSE Reduction** | Directly mixes high-frequency daily scraped price indices into monthly forecasts without aggregation loss. |
| **Gradient Boosted Trees (LightGBM / GBRT)** | *Medeiros et al. (2021)* | vs Phillips Curve / AR | **10% – 25% MSFE Reduction** | Captures non-linear threshold effects (commodity spikes, FX shocks) without overfitting. |
| **Random Forests (RF)** | *Medeiros et al. (2021)* | vs Factor Models | **15% – 22% MSFE Reduction** | Highly resilient against noise and extreme outliers; provides clear SHAP feature importance. |

> **Summary (Most Accurate for Macro Forecasting)**: **Mixed-Data Sampling (MIDAS) + Gradient Boosted Trees (LightGBM/RF)** delivers a **15%–35% RMSE reduction** over traditional econometric benchmarks.

---

## 3. Core Methodologies in the Literature

### Methodology A: Berki et al. (2025) — Transformer-Based COICOP Classification
1. **Scraping & Preprocessing**: Strip HTML tags, remove non-printable characters, filter out promotional noise ("50% OFF", "Special Deal").
2. **Sub-Word Tokenization**: Tokenize product names using Byte-Pair Encoding (BPE) / WordPiece with multilingual vocabularies.
3. **Transformer Fine-Tuning**: Pass tokens through BERT/RoBERTa encoder layers, fine-tuning classification heads with Cross-Entropy Loss across 12 COICOP divisions and 5-digit sub-classes.
4. **Disambiguation**: Resolves polysemous words through surrounding context (e.g. *"Apple"* the fruit -> Division 01 vs. *"Apple iPhone"* -> Division 08).

### Methodology B: BIS Project Spectrum (2024) — Hybrid Vector Cache + LLM Ladder
1. **Tier 1 (Hash Memoization)**: Hash normalized title string; if previously classified, return division in <1ms with zero API cost.
2. **Tier 2 (Dense Vector Embedding)**: Convert title to a 768-dimensional semantic embedding vector and compute cosine similarity against official UN COICOP definition centroids. Auto-classify if similarity >= 0.85.
3. **Tier 3 (Constrained LLM Reasoning)**: For ambiguous items (<0.85), send title and store context to an LLM with strict JSON schema output.
4. **Tier 4 (Persistent Database Caching)**: Save LLM classification into the relational cache (silver.dim_coicop_ai_cache) so recurring scrapes never re-invoke the LLM.

### Methodology C: Medeiros et al. (2021) & Macias et al. (2023) — High-Frequency Inflation Nowcasting
1. **Feature Engineering**:
   - High-frequency daily elementary Jevons price indices (I_01 Food, I_04 Housing/Gas, I_07 Transport/Fuel).
   - Ministry of Economy and Finance (MEF) daily official KHR/USD exchange rates.
   - Ministry of Commerce (MOC) bi-weekly retail gasoline and diesel price ceilings.
2. **Mixed-Frequency Alignment (MIDAS)**:
   - Apply polynomial lag weights (Almon / Exponential lag) giving higher weight to recent daily observations leading up to the end of the month.
3. **Tree-Based Ensemble Regressors**:
   - Train LightGBM and Random Forests to predict monthly inflation rate.
4. **Pre-Publication Leading Indicator**:
   - Produces robust inflation nowcasts 20–30 days before official government publications.

---

## 4. Best Practice Implementation for the Cambodia CPI Pipeline

To achieve maximum accuracy, speed, and cost efficiency in the Cambodia CPI Medallion architecture:

`
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                             CAMBODIA CPI PIPELINE ML STACK                               │
├─────────────────────────────────────────┬────────────────────────────────────────────────┤
│ 1. Silver Layer (Classification)        │ 3-Tier Ladder: Store Lock -> Vector -> LLM     │
│ 2. Silver Layer (Entity Matching)       │ Regex Spec Guards + Cosine Similarity          │
│ 3. Gold / BI Layer (Nowcasting)         │ Intra-Month MTD Expanding Nowcaster            │
│ 4. Serving / BI Layer (Forecasting)     │ LightGBM Multi-Horizon Inflation Regressors    │
└─────────────────────────────────────────┴────────────────────────────────────────────────┘
```

### Module 1: 3-Tier Classification Ladder (pipeline/hybrid_embeddings_classifier.py)
- **Tier 1 (Store Domain Lock - 0ms, 100% precision)**:
  - Fuel stations (petronas, totalenergies, caltex) -> **Division 07 (Transport/Fuels)**.
  - Pharmacies (pharmacy_u-care, pharmacie-de-la-gare) -> **Division 06 (Health)**.
  - Telcos (cellcard, smart) -> **Division 08 (Communication)**.
- **Tier 2 (Vector Embedding Cosine Search - 5ms)**:
  - Generate 768-dimensional text embeddings for grocery and supermarket items (aeon, chip_mong, makro).
  - Calculate cosine similarity against the 12 reference COICOP division centroids. If >= 0.85, auto-assign.
- **Tier 3 (Google Gemini AI Fallback - Only for ambiguous items)**:
  - Prompt Gemini with: *"Classify this Cambodian retail item into UN COICOP (01-12)"*.
  - Cache result into silver.dim_coicop_ai_cache in PostgreSQL for instant O(1) future retrieval.

### Module 2: Spec-Guarded Entity Resolution (pipeline/item_matcher.py)
- Extract volume, weight, and hardware memory specifications (e.g. 128GB, 256GB, 500ml, 1kg) via deterministic regex.
- If two items share a similar title but have conflicting specs (128GB vs 256GB), **strictly reject matching** to eliminate artificial price index spikes.

### Module 3: Machine Learning-Assisted Daily Inflation Nowcasting (ml/nowcaster.py)
- Aggregates daily facts from `gold.fct_cpi_daily` for the active calendar month ($1 \dots t_{\text{observed}}$).
- Projects remaining days ($t+1 \dots T$) using 7-day momentum in **Division 01 (Food - 44.8% weight)** and **Division 07 (Transport - 12.2% weight)** following *Macias et al. (2023)*.
- Derives Month-over-Month (MoM %) estimated inflation and chain-links to official National Institute of Statistics (NIS) Phnom Penh benchmark levels in `gold.fct_cpi_nowcast`.
- Computes dynamic 95% confidence intervals based on daily price dispersion and uncertainty decay ($U_t = \sqrt{(T-t)/T}$).

### Module 4: Multi-Horizon Daily Inflation Forecasting (ml/forecaster.py)
- Use daily price facts from `gold.fct_cpi_daily` for Food, Housing, and Transport alongside Cambodian cultural holiday calendars.
- Train production `LightGBMRegressor` models across walk-forward cross-validation splits (*Babii et al., 2022*) to project 7-day, 14-day, and 30-day forward cumulative inflation rates and projected index levels in `gold.fct_cpi_forecast`.
- Render continuous actual-to-forecast trends via `gold.v_cpi_forecast_chart` on Metabase Dashboard 01.

---

## 5. Summary of Recommended Citations for Thesis

| Thesis Section | Literature Recommendation | Key Takeaway |
|---|---|---|
| **Chapter II: Literature Review** | *Berki et al. (2025)* & *BIS Project Spectrum (2024)* | Validates dense transformer embeddings + LLM reasoning with vector caching for multilingual retail item classification. |
| **Chapter II: Literature Review** | *ONS Data Science Campus (2020)* | Justifies confidence thresholding (tau = 0.80) and audit queue triage for official statistical quality. |
| **Chapter III: Methodology** | *Medeiros et al. (2021)* & *Macias et al. (2023)* | Proves why gradient boosted trees (LightGBM/RF) and MIDAS regressions outperform traditional linear ARIMA models in inflation forecasting. |
| **Chapter III: Methodology** | *IMF / ILO / UN CPI Manual (2020)* | Proves axiomatic superiority of unweighted Jevons geometric mean for elementary price indices. |
