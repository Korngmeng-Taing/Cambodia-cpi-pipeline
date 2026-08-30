# Econometric Pre-CPI Data Visualization & Quality Assurance Framework

> **Reference Standards**: IMF / ILO *Consumer Price Index Manual: Concepts and Methods (2020)*, UN Ottawa Group on Price Indices, Eurostat *Guide on Multilateral Methods*, and MIT *Billion Prices Project (Cavallo & Rigobon)*.

---

## 1. Executive Summary & Mathematical Rationale

Before calculating the elementary-level **Jevons Geometric Mean Index** or aggregating into higher-level **Laspeyres/GEKS Indices**, visual inspection and econometric data screening are essential.

### The Jevons Elementary Index Formula
$$I_J^{0:t} = \prod_{i=1}^{n} \left( \frac{p_{i,t}}{p_{i,0}} \right)^{\frac{1}{n}} = \exp\left( \frac{1}{n} \sum_{i=1}^{n} \ln\left(\frac{p_{i,t}}{p_{i,0}}\right) \right)$$

### Mathematical & Econometric Vulnerabilities
1. **Asymmetry of Log-Ratios**: In logarithmic space, extreme price increases exert asymmetric upward pressure compared to price decreases (e.g. a $10\times$ decimal error yields $\ln(10) \approx +2.30$, whereas a $50\%$ drop yields $\ln(0.5) \approx -0.69$). A small number of uncleaned high-price anomalies will artificially inflate the geometric mean.
2. **The Zero Boundary Disaster**: If a single observation is parsed as zero ($p_{i,t} = 0$), $\ln(0) \to -\infty$, which mathematically collapses the entire elementary index to zero.
3. **Chain Drift & Bouncing**: High-frequency promotional volatility (temporary sales followed by return to regular price) creates asymmetric bouncing and cumulative chain drift in high-frequency web datasets.
4. **Quality Substitution Bias**: Comparing non-identical goods over time violates the **Pure Price Change Principle**, mistaking product specification upgrades (e.g. new package size or technical spec) for general inflation.

---

## 2. End-to-End Pre-CPI Diagnostic Pipeline

```
                         RAW DAILY SCRAPED DATA
                                   │
 ┌─────────────────────────────────┴─────────────────────────────────┐
 │                                                                   │
 ▼                                                                   ▼
[LAYER 1: PRICE LEVEL & VOLATILITY]                 [LAYER 2: BASKET STABILITY & QUALITY]
1. Log-Relative Density (Hadi/Tukey)                4. Longitudinal Survival Matrix
2. Asymmetric Promo Scatter                         5. Semantic Distance Funnel
3. Price Spell Duration Histogram                  6. Imputation Share by Division
                                   │
                                   ▼
                         [GATEWAY VALIDATION]
                                   │
                                   ▼
                    CALCULATE JEVONS & LASPEYRES CPI
```

---

## 3. The 6 Essential Pre-CPI Visualizations

### 1. Log-Price Relative Distributions ($\ln(p_{i,t} / p_{i,t-1})$)
* **Visual Type**: **Histogram / Kernel Density Plot** with a Standard Normal ($N(0, \sigma^2)$) distribution overlay.
* **Econometric Technique**: **Hadi Multivariate Outlier / Tukey Filter** $[Q_1 - k \cdot IQR, Q_3 + k \cdot IQR]$ ($k=1.5$ or $3.0$).
* **Diagnostic Objectives**:
  * **Secondary Bimodal Peaks**: A second small bump at $\ln(r) \approx \pm 2.3$ or $\pm 1.38$ indicates a **$10\times$ decimal error** or **currency conversion bug** (e.g., USD vs KHR exchange rate misapplied).
  * **Fat Heavy Tails**: Identifies unit conversion mix-ups (e.g., 1 gram scraped as 1 kilogram, causing a $1000\times$ spike).
* **Pipeline Rule**: Quarantine and exclude any price observation where $|\ln(p_t / p_{t-1})| > 3.0$ prior to Jevons calculation.

---

### 2. Asymmetric Clearance / "Dump Price" Scatter Plot
* **Visual Type**: **Scatter Plot** ($X$-axis: `discount_pct`, $Y$-axis: `price_relative` $p_t / p_0$, Color: `store_slug`).
* **Econometric Technique**: **Ottawa Group / UK ONS Dump Price Filter**.
* **Diagnostic Objectives**:
  * Clearance sales, damaged stock liquidation, or expiring perishables (e.g., 80–90% off) do not represent true consumer price deflation.
  * When stock clearance ends and the SKU disappears from the website, traditional indices suffer from **asymmetric bouncing** (the price dropped 90%, then disappeared without registering the return to full price).
* **Pipeline Rule**: Flag items with `discount_pct > 70%` as clearance promotions and clamp or exclude them from core elementary indices.

---

### 3. Price Spell Durations & "Sawtooth" Waveform Trajectories
* **Visual Type**: **Multi-Line Time-Series ("Spaghetti Plot")** of individual item price trajectories over 60–90 days.
* **Econometric Technique**: **MIT Billion Prices Project (Cavallo & Rigobon) Sticky Price & Spell Analysis**.
* **Diagnostic Objectives**:
  * In digital retail, true consumer prices follow **"step functions"** (flat horizontal spells with occasional sudden step changes).
  * If an item's trajectory shows a continuous high-frequency zigzag (sawtooth pattern), the scraper is mistakenly conflating multiple distinct SKUs (e.g., alternating between 250ml and 500ml shampoo variants on the same product page).
* **Pipeline Rule**: Re-lock canonical spec guards (pack size, volume, brand) for items exhibiting abnormal trajectory variance.

---

### 4. Product Churn & Longitudinal Matched-Model Survival Matrix
* **Visual Type**: **Heatmap / Grid Matrix** (Rows: Top 100 Canonical Basket SKUs, Columns: Dates, Cell Color: Green = Observed, Grey = Missing/Stockout).
* **Econometric Technique**: **Matched-Model Sample Attrition Matrix**.
* **Diagnostic Objectives**:
  * Web scraped catalogs experience 15%–30% monthly SKU churn (products discontinued, seasonal changes, URL restructuring).
  * If a high-weight item (e.g. *Phka Rumduol Jasmine Rice*) drops off simultaneously across multiple stores, it indicates a scraper parser failure or site-wide blocking rather than a genuine market stockout.
* **Pipeline Rule**: Trigger scraper retry DAGs if store availability drops below 85% before relying on synthetic imputation.

---

### 5. Multi-Modal Semantic Matching & Quality Confidence Distribution
* **Visual Type**: **Histogram of Vector Cosine Similarities ($S \in [0, 1]$)** between newly scraped items and canonical basket definitions.
* **Econometric Technique**: **Hedonic Quality Adjustment & Vector Cosine Thresholding**.
* **Diagnostic Objectives**:
  * **Pure Price vs Quality Change**: CPI must only measure price changes for identical goods. If a scraper matches an *iPhone 13 128GB* to an *iPhone 15 256GB*, the apparent price increase is a quality upgrade, not inflation.
  * The chart should display a sharp bimodal distribution (peaks near $0.95+$ for exact matches and $<0.40$ for unrelated items). Any accumulation in the "ambiguous valley" ($0.50 - 0.80$) represents quality bleed.
* **Pipeline Rule**: Quarantine products scoring between $0.50$ and $0.80$ into `silver.classification_queue` for LLM review or human sign-off.

---

### 6. Imputation Dependency & Weight Vulnerability Area Chart
* **Visual Type**: **100% Stacked Area Chart** by COICOP Division over time ($Y$-axis: Share of Division Basket; Categories: *Live Observed*, *Class-Mean Imputed*, *7-Day Carry-Forward*).
* **Econometric Technique**: **Synthetic Data Exposure Ratio (Eurostat HICP Standard)**.
* **Diagnostic Objectives**:
  * If a division's (e.g., *07 - Transport*) observed share drops below 75% (over 25% imputed), the resulting CPI is essentially simulating prices rather than reflecting market reality.
* **Pipeline Rule**: Block automatic Gold CPI publishing if any major COICOP division's imputation share exceeds the 20% regulatory threshold.

---

## 4. Summary: Pre-CPI Diagnostic Matrix

| Diagnostic Stage | Target Metric / Threshold | Primary Visualization | Pipeline Action if Violated |
| :--- | :--- | :--- | :--- |
| **1. Unit/Decimal Errors** | $|\ln(p_t / p_{t-1})| < 3.0$ | Log-relative density plot | Auto-quarantine to Silver outlier table |
| **2. Dump / Clearance Prices** | `discount_pct < 70%` | Promo vs Relative scatter | Clamp price / flag non-representative |
| **3. SKU Conflation** | Price spell volatility variance | Time-series trajectory plot | Re-lock canonical spec guards |
| **4. Scraper Outages** | Store SKU availability $> 85\%$ | Store-Date survival matrix | Trigger scraper emergency retry DAG |
| **5. Quality Substitution Bias** | Match Cosine $> 0.85$ | Cosine distribution histogram | Route to Gemini AI review queue |
| **6. Synthetic Bias** | Imputation rate $< 15\%$ | Stacked imputation area chart | Block Gold CPI DAG publish |

---

## 5. Key References
1. **International Monetary Fund (IMF), ILO, OECD, Eurostat, UN, World Bank** (2020). *Consumer Price Index Manual: Concepts and Methods*. Washington, DC: International Monetary Fund.
2. **Cavallo, A., & Rigobon, R.** (2016). *The Billion Prices Project: Using Online Prices for Measurement and Research*. Journal of Economic Perspectives, 30(2), 151–178.
3. **United Nations Ottawa Group on Price Indices** (Various Proceedings). *Working Papers on Scanner Data, Web Scraping, and Multilateral Methods*.
4. **Eurostat** (2022). *Guide on Multilateral Methods in the Harmonised Index of Consumer Prices (HICP)*. European Commission.
