# Literature Review: Automated Web-Scraped CPI Pipelines, NLP Classification, and Machine Learning Inflation Nowcasting

> **[!WARNING]**
> **IMPLEMENTATION STATUS (2026-08):** The Gold-layer index computation described in parts of this document - Jevons elementary aggregates, imputation, Laspeyres category/headline roll-ups, GEKS-Tornqvist, Fisher Ideal - is **planned but NOT implemented yet**. Its calculators, dbt models, and gold tables were removed from the codebase.
> Currently live: Bronze ingestion; Silver cleaning / item matching / AI classification / hedonic adjustment; Gold star schema (dim_items, dim_stores, fct_daily_prices); monitoring views. See README "Implementation Status".

This literature review presents key academic and institutional research papers relevant to the **Cambodia Daily Consumer Price Index (CPI) Medallion Pipeline**. The papers are organized into four core pillars that mirror the project's architecture:
1. **Web Scraping & High-Frequency Online Price Ingestion for CPI Compilation**
2. **Natural Language Processing & Machine Learning for Automated COICOP Product Classification**
3. **Econometric Multilateral Price Aggregation & Substitution Bias Handling (GEKS, Fisher, Jevons)**
4. **Machine Learning & Time-Series Forecasting / Nowcasting of Headline & Component CPI**

---

## Comparative Literature Matrix

| # | Paper Title | Authors | Year | Focus Area | Key Methodology | Reported Accuracy / Performance Metrics | Link / Reference |
|:---|:---|:---|:---:|:---|:---|:---|:---|
| **1** | **The Billion Prices Project: Using Online Prices for Measurement and Research** | Alberto Cavallo, Roberto Rigobon | 2016 | Online Price Scraping & Daily Inflation | Automated daily web crawlers, unweighted geometric averages, official CPI basket matching across 22 countries | 98%+ correlation with official monthly CPI; detected inflation turning points and macro shocks weeks ahead of official NSI releases | [doi:10.1257/jep.30.2.151](https://doi.org/10.1257/jep.30.2.151) |
| **2** | **NLP-Enhanced Inflation Measurement Using BERT and Web Scraping** | Martin Berki, Vanesa Andicsova, Milos Oravec | 2025 | Web Scraping + Deep NLP COICOP Mapping | Scraping e-commerce portals, fine-tuned transformer (BERT) classification into COICOP categories, daily index compilation | **94.56% classification accuracy**, 94.07% weighted precision; dynamic price volatility tracking superior to monthly survey benchmarks | [doi:10.3389/frai.2025.1543026](https://doi.org/10.3389/frai.2025.1543026) |
| **3** | **Nowcasting Food Inflation with a Massive Amount of Online Prices** | Paweł Macias, Damian Stelmasiak, Karol Szafranek | 2023 | High-Frequency Scraped Data & Nowcasting | Millions of daily food scraped quotes, ECOICOP item matching, mixed-frequency recursive time-series models | **15% to 35% reduction in RMSE** compared to standard AR/ARIMA benchmarks; real-time tracking during COVID-19 shock | [doi:10.1016/j.ijforecast.2022.01.007](https://doi.org/10.1016/j.ijforecast.2022.01.007) |
| **4** | **Forecasting Inflation in a Data-Rich Environment: The Benefits of Machine Learning Methods** | Marcelo C. Medeiros, Gabriel F. R. Vasconcelos, Álvaro Veiga, Eduardo Zilberman | 2021 | Machine Learning Inflation Forecasting | High-dimensional macroeconomic feature space, Random Forests, Gradient Boosted Trees (GBRT), LASSO, Ridge | **Significantly lower MSFE/RMSE** (10–25% gain) over U.S. Phillips Curve, AR benchmarks, and Factor Models across 1 to 12-month horizons | [doi:10.1080/07350015.2019.1637745](https://doi.org/1080/07350015.2019.1637745) |
| **5** | **Web Scraping Techniques to Collect Data on Consumer Prices and Machine Learning for Product Classification** | Federico Polidoro, Roberto Giannini, Rosanna Lo Conte, Silvia Rossetti | 2015 | Scraper Infrastructure & Supervised ML Classification | Custom crawler pipeline for e-commerce sites, text tokenization, Naive Bayes, Support Vector Machines (SVM) for item grouping | **82% to 92% classification accuracy** across consumer tech and airfare; paved the standard for European National Statistical Institutes (NSIs) | [doi:10.3233/SJI-150896](https://doi.org/10.3233/SJI-150896) |
| **6** | **A New Methodology for Processing Scanner Data in the Dutch CPI** | Antonio G. Chessa | 2016 | Scanner Data & Multilateral Index Formulas | Characteristic-based item matching, rolling multilateral GEKS-Törnqvist (QU-GEKS), Movement/Half-Splice linking | Eliminated chain drift and downward substitution bias completely across volatile retail supermarket turnover | [EURONA 1/2016](https://ec.europa.eu/eurostat/cros/content/eurona-issue-1-2016_en) |
| **7** | **Substitution Bias and Scanner Data: Measuring Price Change with Scanner Data** | W. Erwin Diewert, Kevin J. Fox | 2020 | Micro Econometric Index Theory & Superlative Indexes | Superlative Fisher Ideal and Törnqvist multilateral indices compared to fixed-base Laspeyres on high-frequency barcode scanner data | Quantified substitution bias ($0.3\%$ to $0.8\%$ per annum); proved Superlative Fisher/Törnqvist satisfies axiomatic index tests | [doi:10.1016/j.jeconom.2019.12.013](https://doi.org/10.1016/j.jeconom.2019.12.013) |
| **8** | **Project Spectrum: Using Generative AI to Enhance Inflation Nowcasting** | Bank for International Settlements (BIS), ECB, Deutsche Bundesbank | 2024–2026 | LLMs & Embeddings for Web-Scraped Data | Large Language Models (LLMs), semantic text embeddings, automated item taxonomy mapping on billions of price quotes | **95%+ classification precision** on multi-language unstructured retailer catalogues, outperforming traditional keyword heuristics | [BIS Project Spectrum Report](https://www.bis.org/about/bisih/topics/ai/spectrum.htm) |
| **9** | **Using Machine Learning for Classifying Web-Scraped Clothing Data** | Office for National Statistics (ONS, UK) | 2020 | NLP & Machine Learning for NSI Production | TF-IDF text features, FastText, XGBoost classifier with Human-in-the-Loop confidence thresholds for COICOP Level 4/5 | **87% to 91% F1-score** on complex apparel categories; reduced manual NSI coding burden by over 70% | [ONS Digital Publishing](https://www.ons.gov.uk/economy/inflationandpriceindices/methodologies) |
| **10** | **Consumer Price Index Manual: Concepts and Methods** | IMF, ILO, OECD, Eurostat, UN, World Bank | 2020 | International Standards & Index Axioms | Elementary Jevons geometric mean, Dutot/Carli evaluation, Laspeyres upper-level aggregation, multilateral GEKS, hedonic quality adjustment | Official global standard establishing Jevons as the preferred elementary aggregate and GEKS for scanner/web-scraped big data | [IMF eLibrary ISBN: 9781484354308](https://www.elibrary.imf.org/display/book/9781484354308/9781484354308.xml) |

---

## Detailed Literature Review Profiles

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                               PIPELINE ARCHITECTURAL MAPPING                                │
├───────────────────────────────┬─────────────────────────────┬───────────────────────────────┤
│ PROJECT COMPONENT             │ KEY METHODOLOGIES           │ PRIMARY ACADEMIC LITERATURE   │
├───────────────────────────────┼─────────────────────────────┼───────────────────────────────┤
│ 1. Bronze (Web Scraping)      │ Automated daily scrapers    │ Cavallo & Rigobon (2016),     │
│                               │ multi-source crawlers       │ Polidoro et al. (2015)        │
│ 2. Silver (Classification)    │ BERT, LLM cache, RapidFuzz, │ Berki et al. (2025),          │
│                               │ XGBoost, COICOP hierarchy   │ ONS (2020), BIS (2024/2026)   │
│ 3. Gold (Econometrics)        │ Jevons, Laspeyres, GEKS,    │ Chessa (2016),                │
│                               │ Superlative Fisher, Splice  │ Diewert & Fox (2020), IMF     │
│ 4. Prediction & Nowcasting    │ Random Forest, XGBoost,     │ Macias et al. (2023),         │
│                               │ LSTM, Prophet, Exogenous    │ Medeiros et al. (2021)        │
└───────────────────────────────┴─────────────────────────────┴───────────────────────────────┘
```

---

### Paper 1: The Billion Prices Project: Using Online Prices for Measurement and Research
* **Title**: *The Billion Prices Project: Using Online Prices for Measurement and Research*
* **Authors**: Alberto Cavallo and Roberto Rigobon
* **Publish Year**: 2016
* **Publication Venue**: *Journal of Economic Perspectives*, Vol. 30, No. 2, pp. 151–178
* **Purpose**: To demonstrate how daily, automated web scraping across hundreds of online retailers in dozens of countries can construct real-time consumer price indices, track high-frequency inflation dynamics, and eliminate the multi-week lag inherent in traditional manual field-agent price surveys.
* **Methodology**: 
  * Custom software scrapers extracting daily product prices, detailed item descriptions, brands, and categories from multichannel and pure e-commerce retailers across 22 countries.
  * Constructing micro-price panels and calculating unweighted geometric mean price relatives (Jevons formula) at the elementary level, aggregated up to headline indices using national expenditure weights.
* **Accuracy / Quantitative Results**:
  * Scraped online price indices maintained a correlation exceeding **0.98** with official monthly Consumer Price Indices in low-inflation economies (US, UK, Germany, Brazil).
  * In economies experiencing statistical tampering or high inflation volatility (e.g., Argentina 2007–2015), the online index accurately detected true annual inflation of ~20% when official statistics reported only 8%.
  * Provided immediate detection of macroeconomic exchange rate passthrough shocks within 3 to 14 days.
* **Link Reference**: [https://doi.org/10.1257/jep.30.2.151](https://doi.org/10.1257/jep.30.2.151)

---

### Paper 2: NLP-Enhanced Inflation Measurement Using BERT and Web Scraping
* **Title**: *NLP-enhanced inflation measurement using BERT and web scraping*
* **Authors**: Martin Berki, Vanesa Andicsova, and Milos Oravec
* **Publish Year**: 2025
* **Publication Venue**: *Frontiers in Artificial Intelligence*, Vol. 8, Article 1543026 (AI in Finance Section)
* **Purpose**: To bridge the gap between unstructured, noisy web-scraped e-commerce data and official statistical classification hierarchies by deploying transformer-based Natural Language Processing (NLP) models to categorize online products into COICOP divisions and calculate dynamic price indices.
* **Methodology**:
  * Web scraped thousands of detailed product listings from online price comparison platforms and consumer retail portals.
  * Fine-tuned a Bidirectional Encoder Representations from Transformers (**BERT**) neural model to process multilingual and abbreviated product names into standardized 5-digit COICOP categories.
  * Generated high-frequency, category-level and headline indices, analyzing how automated NLP classification compares to official statistical HICP benchmarks.
* **Accuracy / Quantitative Results**:
  * Achieved a classification **Accuracy of 94.56%** on held-out validation data.
  * Achieved **94.07% Weighted Precision** and **79.41% Macro Precision** across complex technical categories.
  * Showed that NLP-driven daily price index compilation captured high-volatility product turnover and promotional discounting that standard monthly static surveys miss.
* **Link Reference**: [https://doi.org/10.3389/frai.2025.1543026](https://doi.org/10.3389/frai.2025.1543026)

---

### Paper 3: Nowcasting Food Inflation with a Massive Amount of Online Prices
* **Title**: *Nowcasting food inflation with a massive amount of online prices*
* **Authors**: Paweł Macias, Damian Stelmasiak, and Karol Szafranek
* **Publish Year**: 2023
* **Publication Venue**: *International Journal of Forecasting*, Vol. 39, Issue 2, pp. 809–826
* **Purpose**: To evaluate whether scraping massive volumes of daily online grocery and supermarket prices can provide accurate, real-time nowcasts and forecasts of official monthly food CPI before official statistical office announcements.
* **Methodology**:
  * Daily web scraping of millions of price observations from leading retail chains in Poland between 2009 and 2020.
  * Automated mapping of scraped product titles into detailed ECOICOP categories, combined with out-of-sample recursive forecasting frameworks (Mixed-Data Sampling / MIDAS, autoregressive distributed lag models, and dynamic model averaging).
* **Accuracy / Quantitative Results**:
  * Demonstrated a **15% to 35% reduction in Root Mean Square Error (RMSE)** across forecasting horizons compared to standard benchmark econometric models (AR, ARIMA, Random Walk).
  * Outperformed central bank and private consensus survey forecasts during volatile market shocks (including the COVID-19 pandemic price spikes).
* **Link Reference**: [https://doi.org/10.1016/j.ijforecast.2022.01.007](https://doi.org/10.1016/j.ijforecast.2022.01.007)

---

### Paper 4: Forecasting Inflation in a Data-Rich Environment: The Benefits of Machine Learning Methods
* **Title**: *Forecasting Inflation in a Data-Rich Environment: The Benefits of Machine Learning Methods*
* **Authors**: Marcelo C. Medeiros, Gabriel F. R. Vasconcelos, Álvaro Veiga, and Eduardo Zilberman
* **Publish Year**: 2021
* **Publication Venue**: *Journal of Business & Economic Statistics*, Vol. 39, Issue 1, pp. 98–119
* **Purpose**: To conduct a comprehensive empirical evaluation of machine learning models versus traditional econometric methods for forecasting headline and core inflation in environments with large numbers of macroeconomic, financial, and commodity price variables.
* **Methodology**:
  * Tested regularized linear models (LASSO, Adaptive LASSO, Elastic Net, Ridge), Factor Models, and non-linear machine learning ensembles (**Random Forest**, **Gradient Boosted Trees / GBRT**, Support Vector Regression).
  * Evaluated across forecasting horizons $h = 1, 3, 6, 12$ months using expanding-window out-of-sample backtesting.
* **Accuracy / Quantitative Results**:
  * **Random Forest (RF)** and Gradient Boosted Trees consistently dominated all traditional benchmarks (AR, Phillips Curve, Dynamic Factor Models), yielding statistically significant reductions in Mean Squared Forecast Error (**MSFE / RMSE reduced by 10% to 25%**).
  * Demonstrated that machine learning models effectively capture non-linear relationships and interactions between exchange rates, commodity inputs, and seasonal shocks without overfitting.
* **Link Reference**: [https://doi.org/10.1080/07350015.2019.1637745](https://doi.org/1080/07350015.2019.1637745)

---

### Paper 5: Web Scraping Techniques to Collect Data on Consumer Prices and Machine Learning for Product Classification
* **Title**: *Web scraping techniques to collect data on consumer prices and machine learning for product classification*
* **Authors**: Federico Polidoro, Roberto Giannini, Rosanna Lo Conte, and Silvia Rossetti
* **Publish Year**: 2015
* **Publication Venue**: *Statistical Journal of the IAOS*, Vol. 31, No. 3, pp. 447–461
* **Purpose**: To pioneer the technical architecture for national statistical offices (ISTAT) to integrate daily automated web scraping and supervised machine learning algorithms into official Consumer Price Index (CPI) and Harmonised Index of Consumer Prices (HICP) production.
* **Methodology**:
  * End-to-end data pipeline: web scrapers targeting consumer electronics and airfare portals $\to$ raw data parsing $\to$ text preprocessing and normalization $\to$ supervised classifiers (Naive Bayes and Support Vector Machines) mapping product listings to European ECOICOP classes.
* **Accuracy / Quantitative Results**:
  * Classification accuracy reached **82.0% to 92.5%** depending on product category verbosity and structural complexity.
  * Proved that automated web scraping drastically increases quote sample sizes by orders of magnitude (from hundreds of manual monthly quotes to tens of thousands of daily quotes) while slashing operational data collection costs.
* **Link Reference**: [https://doi.org/10.3233/SJI-150896](https://doi.org/10.3233/SJI-150896)

---

### Paper 6: A New Methodology for Processing Scanner Data in the Dutch CPI
* **Title**: *A New Methodology for Processing Scanner Data in the Dutch CPI*
* **Authors**: Antonio G. Chessa
* **Publish Year**: 2016
* **Publication Venue**: *EURONA – Eurostat Review on National Accounts and Macroeconomic Indicators*, Issue 1/2016, pp. 49–69
* **Purpose**: To solve the severe index distortion known as "chain drift" and handle massive product turnover in high-frequency scanner and web-scraped datasets through the implementation of multilateral index calculation methods.
* **Methodology**:
  * Characteristic-based product definition and automated entity matching.
  * Rolling 13-month and 25-month **GEKS-Törnqvist** (and Quality-Adjusted Unit Value GEKS / QU-GEKS) multilateral systems combined with **Movement Splice** and **Half-Splice** window updating mechanisms to preserve transitivity and avoid circularity bias.
* **Accuracy / Quantitative Results**:
  * Completely eliminated downward chain drift (which caused bilateral chained Jevons/Laspeyres indices to diverge by up to 5–10% per year due to retail clearance sales).
  * Adopted as the official production methodology by Statistics Netherlands (CBS) and endorsed by Eurostat for processing millions of weekly supermarket barcode records.
* **Link Reference**: [https://ec.europa.eu/eurostat/cros/content/eurona-issue-1-2016_en](https://ec.europa.eu/eurostat/cros/content/eurona-issue-1-2016_en)

---

### Paper 7: Substitution Bias and Scanner Data: Measuring Price Change with Scanner Data
* **Title**: *Substitution Bias and Scanner Data: Measuring Price Change with Scanner Data*
* **Authors**: W. Erwin Diewert and Kevin J. Fox
* **Publish Year**: 2020
* **Publication Venue**: *Journal of Econometrics*, Vol. 217, Issue 2, pp. 268–284
* **Purpose**: To quantify the magnitude of consumer substitution bias in fixed-basket Laspeyres CPI formulas using granular transaction microdata, and to formulate axiomatic superlative index methods that accurately capture consumer price elasticity.
* **Methodology**:
  * Compared bilateral and multilateral index formulas: Fixed-base Laspeyres, Paasche, **Superlative Fisher Ideal Index** ($P_F = \sqrt{P_L \times P_P}$), and Törnqvist index.
  * Applied economic index number theory and distance functions to prove that superlative indices provide second-order approximations to true arbitrary consumer expenditure functions.
* **Accuracy / Quantitative Results**:
  * Found that traditional fixed-base Laspeyres indices overstate true cost-of-living inflation by **0.30% to 0.85% annually** due to commodity substitution bias (consumers substituting towards goods whose relative prices fall).
  * Proved that superlative Fisher and multilateral Törnqvist systems satisfy all major axiomatic index criteria (transitivity, time-reversal, and price bounce resilience).
* **Link Reference**: [https://doi.org/10.1016/j.jeconom.2019.12.013](https://doi.org/10.1016/j.jeconom.2019.12.013)

---

### Paper 8: Project Spectrum: Using Generative AI to Enhance Inflation Nowcasting
* **Title**: *Project Spectrum: Using generative AI to enhance inflation nowcasting*
* **Authors**: Bank for International Settlements (BIS) Innovation Hub, European Central Bank (ECB), and Deutsche Bundesbank
* **Publish Year**: 2024–2026
* **Publication Venue**: *BIS Innovation Hub Technical Reports & ECB Working Series*
* **Purpose**: To harness Generative AI (Large Language Models) and dense text embeddings to process billions of multilingual, unstructured web-scraped retail price observations into standardized COICOP taxonomies for real-time central bank inflation nowcasting.
* **Methodology**:
  * Automated web scraping across thousands of retail e-commerce domains.
  * Utilizing dense semantic text embeddings and LLM reasoning engines (with vector database caching) to perform zero-shot and few-shot classification of messy product titles into 5-digit COICOP 2018 categories.
  * Aggregating classified micro-prices into high-frequency nowcasting models for central bank monetary policy analysis.
* **Accuracy / Quantitative Results**:
  * Achieved **>95% Classification Precision** on multilingual, abbreviated item titles, drastically outperforming legacy regex rules and dictionary tables.
  * Reduced latency of item classification pipeline from days to minutes through memoized embedding caches.
* **Link Reference**: [https://www.bis.org/about/bisih/topics/ai/spectrum.htm](https://www.bis.org/about/bisih/topics/ai/spectrum.htm)

---

### Paper 9: Using Machine Learning for Classifying Web-Scraped Clothing Data
* **Title**: *Using machine learning for classifying web-scraped data into COICOP*
* **Authors**: Office for National Statistics (ONS, United Kingdom) Data Science Campus & Prices Division
* **Publish Year**: 2020 (Updated 2021)
* **Publication Venue**: *ONS Technical Methodology Papers & Eurostat Big Data Proceedings*
* **Purpose**: To build an automated, scalable machine learning classification pipeline capable of sorting millions of web-scraped apparel items into COICOP 4-digit and 5-digit categories with an integrated human-in-the-loop review workflow.
* **Methodology**:
  * Text cleaning and feature extraction using TF-IDF and word embeddings (FastText).
  * Trained and compared supervised algorithms: Logistic Regression, Random Forest, and **XGBoost (Extreme Gradient Boosting)**.
  * Designed confidence thresholding gates ($Threshold \ge 0.80$) where confident predictions are ingested automatically and borderline predictions are routed to human triage.
* **Accuracy / Quantitative Results**:
  * XGBoost achieved an overall **Macro F1-Score of 87% to 91%** across volatile clothing and footwear sub-classes.
  * Automated more than **70% of the classification volume** without any manual human intervention, maintaining official National Statistics quality compliance.
* **Link Reference**: [https://www.ons.gov.uk/economy/inflationandpriceindices/methodologies](https://www.ons.gov.uk/economy/inflationandpriceindices/methodologies)

---

### Paper 10: Consumer Price Index Manual: Concepts and Methods
* **Title**: *Consumer Price Index Manual: Concepts and Methods*
* **Authors**: International Monetary Fund (IMF), International Labour Organization (ILO), OECD, Eurostat, United Nations, and World Bank
* **Publish Year**: 2020
* **Publication Venue**: *IMF Publication Services, Washington D.C.* (ISBN: 978-1-48435-430-8)
* **Purpose**: To provide the definitive global standard, econometric formulas, and best practices for national statistical offices and data scientists compiling Consumer Price Indices using traditional surveys, web-scraped data, and barcode scanner datasets.
* **Methodology**:
  * Formulates mathematical properties of elementary aggregates: **Jevons Geometric Mean** ($P_J$), Dutot ($P_D$), and Carli ($P_C$).
  * Demonstrates that the Carli index suffers from severe upward bias and fails the time-reversal test ($I_{0,t} \times I_{t,0} \neq 1$), whereas the **Jevons index is transitive and satisfies the axiomatic test approach**.
  * Outlines upper-level Laspeyres basket weighting, log-linear Hedonic Quality Adjustments for high-tech items, and multilateral GEKS-Törnqvist methods for high-frequency alternative data.
* **Accuracy / Quantitative Results**:
  * Established Jevons as the international baseline elementary formula, proving mathematically that it avoids the $0.5\% - 1.5\%$ upward aggregation bias of the Carli formula.
* **Link Reference**: [https://www.elibrary.imf.org/display/book/9781484354308/9781484354308.xml](https://www.elibrary.imf.org/display/book/9781484354308/9781484354308.xml)

---

## Synthesis & Relevance to the Cambodia CPI Medallion Pipeline

| Research Finding from Literature | Direct Implementation in Your Medallion Pipeline |
|:---|:---|
| **Daily Web Scraping Ingestion** *(Cavallo & Rigobon 2016)* | **Bronze Layer (Active)**: 20 scrapers orchestrated daily via Apache Airflow across all 12 UN COICOP divisions (AEON, DeliShop, L192, Khmer24, redBus, MOC Fuel, MEF FX). |
| **Hybrid NLP / LLM Classification** *(Berki et al. 2025; BIS Spectrum 2024)* | **Silver Layer (Active)**: 4-tier classification ladder: Human Overrides $\to$ Store Domain Purity $\to$ **Google Gemini AI Flash memoized cache** (`silver.dim_coicop_ai_cache`) $\to$ Taxonomy fallback. |
| **Canonical Entity Matching** *(Polidoro et al. 2015; Chessa 2016)* | **Silver Layer (Active)**: Python `ItemMatcher` using exact barcode/SKU matching + RapidFuzz Token-Sort fuzzy similarity ($\ge 0.95$) + Gemini Item Reviewer. |
| **Hedonic Quality Adjustment** *(IMF Manual 2020; Diewert 2020)* | **Silver Layer (Active)**: Multi-attribute log-linear hedonic regression (`pipeline/hedonic_regression.py`) evaluated across high-tech electronics characteristics. |
| **Elementary Jevons & Superlative Indexes** *(IMF Manual 2020; Diewert & Fox 2020)* | **Gold Layer (Planned)**: Elementary Geometric Mean (`fct_jevons_daily`), Laspeyres Aggregation (`gold.cpi_headline_daily`), and Superlative Fisher Ideal Index (designed in `docs/GOLD_LAYER_IMPLEMENTATION_PLAN.md`). |
| **Multilateral GEKS-Törnqvist** *(Chessa 2016; Eurostat Guide)* | **Gold Layer (Planned)**: Multilateral GEKS-Törnqvist with rolling 13-period Movement Splicing to eliminate chain drift (designed in `docs/GOLD_LAYER_IMPLEMENTATION_PLAN.md`). |
| **Machine Learning Inflation Forecasting** *(Medeiros et al. 2021; Macias et al. 2023)* | **Prediction Layer (Future Extension)**: Machine learning models leveraging daily price momentum, exchange rates, and fuel regressors. |
