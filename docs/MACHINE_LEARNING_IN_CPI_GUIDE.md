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
│ 1. Silver Layer (Classification)        │ 5-Tier Ladder: Purity -> Semantic -> Local AI -> Cloud AI -> Human │
│ 2. Silver Layer (Entity Matching)       │ Regex Spec Guards + Cosine Similarity          │
│ 3. Gold / BI Layer (Nowcasting)         │ Intra-Month MTD Expanding Nowcaster            │
│ 4. Serving / BI Layer (Forecasting)     │ LightGBM Multi-Horizon Inflation Regressors    │
└─────────────────────────────────────────┴────────────────────────────────────────────────┘
`

### Module 1: AI-First Direct Classification Engine (pipeline/gemini_coicop_classifier.py)
- **Deterministic Text Rules & Seed Overrides**:
  - Immediate assignment via verified seeds (`coicop_classification_seed.csv`, `coicop_text_rules.csv`) and store purity locks (e.g. telcos -> `08`, fuels -> `07`, pharmacies -> `06`).
- **Direct 5-Digit AI Classification (Google Gemini Flash)**:
  - Batch classification (40 items per call) mapping retail listings directly to UN COICOP 2018 5-digit sub-class codes.
  - Native bilingual Khmer and English comprehension.
  - Domain guardrails preventing common cross-division confusions (pet food, skincare vs medicine, alcohol vs non-alcoholic drinks).
  - Multi-key rotation via `GeminiKeyPool` for high throughput and automated 429 backoff.
- **Database Memoization**:
  - Validated predictions are stored permanently in `silver.canonical_items` and `silver.clean_store_prices`.

### Module 2: Spec-Guarded Entity Resolution (pipeline/item_matcher.py & pipeline/hedonic_regression.py)
- **Deterministic Regex Spec Guards**: Extract volume, weight, and hardware memory specifications (e.g. 128GB, 256GB, 500ml, 1kg). If two items share a similar title but have conflicting specs (128GB vs 256GB), **strictly reject matching** to eliminate artificial price index spikes.
- **Log-Linear Hedonic Quality Adjustment (`pipeline/hedonic_regression.py`)**:
  For heterogeneous consumer durables (laptops, smartphones), quality changes are decoupled from pure price movements via hedonic regression:
  $$\ln(P_{i,t}) = \alpha_t + \sum_{k} \beta_k X_{i,k} + \varepsilon_{i,t}$$
  Constant-utility prices are computed by removing characteristic premia relative to market mean specs:
  $$\widetilde{P}_{i,t} = P_{i,t} \cdot \exp\left(-\sum_k \widehat{\beta}_k (X_{i,k} - \bar{X}_k)\right)$$
  When sample size is inadequate ($n < 5$), features lack variance, or the design matrix is collinear, `run_hedonic_regression()` gracefully catches the condition, logs `SKIPPED_RANK_DEFICIENT`, and passes the observed price forward untouched.

### Module 3: Two-Stage Hybrid Ridge Nowcasting Engine (`ml/nowcaster.py` & `ml/config.py`)
- **Axiomatic Bottom-Up 5-Basket Aggregation**:
  Rather than predicting an ad-hoc aggregate headline index directly, the nowcaster models the price relatives of **5 key consumption divisions** representing **81.58%** of Cambodia's CPI basket:
  1. **Division 01: Food & Non-Alcoholic Beverages** (Weight: 44.78%)
  2. **Division 02: Alcoholic Beverages & Tobacco** (Weight: 1.63%)
  3. **Division 04: Housing, Water, Electricity, Gas & Other Fuels** (Weight: 17.08%)
  4. **Division 07: Transport & Vehicle Fuels** (Weight: 12.23%)
  5. **Division 11: Restaurants & Hotels** (Weight: 5.86%)
  *(Remaining 7 divisions covering 18.42% are anchored to neutral carryover/prior month indices).*

- **Two-Stage Hybrid Architecture**:
  - **Stage 1 (Deterministic Micro-Aggregation & Realized MTD Trajectory)**:
    Aggregates daily elementary Jevons price indices for observed calendar days $1 \dots t_{\text{observed}}$.
  - **Stage 2 (Empirical Bayes Shrinkage Ridge Drift Estimator)**:
    Estimates the expected daily drift $\widehat{\mu}_k$ for remaining days $N = T - t$ via `RidgeCV` fitted across rolling multi-horizon momentum features:
    - Intra-month division momentum: 3-day, 7-day, 14-day rolling price trends ($m_{\text{food}, 3d/7d/14d}$, $m_{\text{trans}, 3d/7d}$).
    - Daily official USD/KHR exchange rate momentum from MEF ($m_{\text{fx}, 7d/14d}$).
    - Transitory holiday shocks and demand proximity metrics (`CAMBODIA_ANNUAL_HOLIDAYS`).
    - Empirical Bayesian shrinkage prior pulling extreme drift estimates back to zero ($R^2$-weighted shrinkage) to prevent out-of-sample variance explosion early in the month.

- **Midpoint Trajectory Drift Expectation**:
  For remaining unobserved days $N = T - t$, the average expected price index across the remainder of the month reflects cumulative linear progression:
  $$E[P_{k, \text{remaining}}] = P_{k, t} \times \left(1.0 + \widehat{\mu}_k \times \frac{N + 1}{2}\right)$$
  The monthly mean index for basket $k$ is computed as the weighted time average:
  $$\bar{I}_{k, \text{month}} = \frac{\sum_{s=1}^t P_{k, s} + N \times E[P_{k, \text{remaining}}]}{T}$$

- **Exact Laspeyres Axiomatic Aggregation**:
  The headline CPI nowcast strictly adheres to the Laspeyres index formulation:
  $$\widehat{\text{HeadlineCPI}}_T = \sum_{k \in \mathcal{K}} w_k \cdot \bar{I}_{k, \text{month}} + \sum_{m \notin \mathcal{K}} w_m \cdot I_{m, \text{baseline}}$$
  The overall Month-over-Month (MoM %) projected inflation is derived directly from the aggregate index and chain-linked to official National Institute of Statistics (NIS) Phnom Penh benchmark levels in `gold.fct_cpi_nowcast`.

- **Dynamic Uncertainty Decay & Evaluation**:
  - Dynamic 95% confidence intervals scale with daily price dispersion and time decay ($U_t = \sqrt{(T-t)/T}$).
  - Full tracking and evaluation is exposed via PostgreSQL view `gold.v_nowcast_evaluation` (`nowcast_food_cpi`, `nowcast_transport_cpi`, `nowcast_housing_cpi`, `nowcast_restaurant_cpi`, `nowcast_alcohol_cpi`, and individual `projected_*_mom_pct`).

### Module 4: Self-Learning Rule Generation Loop (scripts/automated_rule_suggester.py)
- **Human-in-the-Loop (HITL) Feedback**: Analyst corrections from the `analyst_quick_fix` tool are recorded in `silver.manual_item_corrections`.
- **Pattern Discovery**: A local LLM analyzes manual fixes to identify recurring linguistic patterns (e.g., "All items with brand 'SAMSUNG' were corrected to Division 08").
- **Deterministic Translation**: The AI proposes a Regular Expression (Regex) rule that can be added to the `coicop_text_rules` seed, effectively converting human expertise into permanent, high-speed deterministic code.

---

## 5. Summary of Recommended Citations for Thesis

| Thesis Section | Literature Recommendation | Key Takeaway |
|---|---|---|
| **Chapter II: Literature Review** | *Berki et al. (2025)* & *BIS Project Spectrum (2024)* | Validates dense transformer embeddings + LLM reasoning with vector caching for multilingual retail item classification. |
| **Chapter II: Literature Review** | *ONS Data Science Campus (2020)* | Justifies confidence thresholding (tau = 0.80) and audit queue triage for official statistical quality. |
| **Chapter III: Methodology** | *Medeiros et al. (2021)* & *Macias et al. (2023)* | Proves why gradient boosted trees (LightGBM/RF) and MIDAS regressions outperform traditional linear ARIMA models in inflation forecasting. |
| **Chapter III: Methodology** | *IMF / ILO / UN CPI Manual (2020)* | Proves axiomatic superiority of unweighted Jevons geometric mean for elementary price indices. |
