# Recommended CPI Methodology: Two-Tier Hybrid Lowe-Jevons Framework

**Document Title:** Standard Operating Methodology for Cambodia Daily E-Commerce CPI Pipeline  
**Methodological Standard:** IMF / ILO / OECD / Eurostat / UN / World Bank *Consumer Price Index Manual: Concepts and Methods (2020)*  
**Target Application:** High-Frequency Web-Scraped Store Prices + Official NIS Cambodia CSES Weights  

---

## 1. Executive Summary

This document establishes the official mathematical and algorithmic methodology recommended for the **Cambodia Daily Consumer Price Index (CPI) Pipeline**.

Because web-scraped supermarket prices lack point-of-sale transaction volumes ($q_{i,t}$), direct superlative price indices (e.g., Fisher, Törnqvist) cannot be computed at the item level. To achieve international compliance, statistical robustness, and zero chain drift, this pipeline adopts a **Two-Tier Hybrid Lowe-Jevons Framework**:

1. **Micro/Elementary Level (Tier 1 & 2):** Unweighted **Jevons Geometric Mean Index** with **Targeted Class-Mean Imputation** for missing varieties and **Tukey Boxplot Outlier Filtering**.
2. **Macro/Aggregate Level (Tier 3, 4 & 5):** Fixed-base **Lowe / Young Index** utilizing official expenditure shares from the **Cambodia Socio-Economic Survey (CSES)** published by the **National Institute of Statistics (NIS)**.

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                          5-TIER CPI AGGREGATION PYRAMID                                 │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│ Tier 5: National Headline & Core CPI                                                    │
│    ▲                                                                                    │
│    │ Laspeyres/Lowe Aggregation (12 Official NIS Division Weights, W_d)                 │
│ Tier 4: 12 UN COICOP Divisions (e.g., Division 01 Food = 44.800%)                       │
│    ▲                                                                                    │
│    │ Intra-Division Expenditure Weights (w_c|d)                                         │
│ Tier 3: 4-Digit COICOP Subclasses (e.g., 01.1.1 Rice & Cereals = 41.295% of Food)       │
│    ▲                                                                                    │
│    │ Jevons Elementary Aggregate Index (Equal Item Weight: 1/N_c)                       │
│ Tier 2: Canonical Item-Level Price Relatives (I_i^(t/0))                                │
│    ▲                                                                                    │
│    │ Unit Price Standardization (Price in KHR / Standard Unit)                          │
│ Tier 1: Raw Multi-Store Daily Web Scrapes                                               │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. End-to-End Mathematical Formulation

### Tier 1: Unit Price Normalization & Data Editing

To prevent **shrinkflation bias** (e.g., package shrinking from 500g to 400g at constant nominal price), all raw prices are converted to standardized unit prices:

$$\tilde{P}_{i, s, t} = \frac{\text{Observed Price}_{\text{KHR}}}{\text{Normalized Volume/Weight}} \quad [\text{KHR per kg, L, or unit}]$$

#### Outlier Filtering (Tukey Algorithmic Bounds - Chapter 5, Annex 5.3)
Price relatives showing sudden implausible jumps (scraper parsing glitches) are detected on log ratios:

$$r_{i,t} = \ln\left(\frac{\tilde{P}_{i,t}}{\tilde{P}_{i,t-1}}\right)$$

Observations falling outside the interquartile range are flagged for manual review or excluded:

$$\text{Valid Range} = [Q_1 - c \cdot IQR, \; Q_3 + c \cdot IQR] \quad (c = 3.0 \text{ for extreme outliers})$$

---

### Tier 2: Missing Price Imputation & Elementary Micro-Indices

#### 1. Targeted Compounded Class-Mean Imputation (Chapter 6, §6.55)
When an item $i$ in subclass $c$ is temporarily out of stock on day $t$ (gap $\Delta t \le 7$ days):

$$\widehat{P}_{i,t} = P_{i,t-\Delta t} \times \left( \prod_{j \in \text{Observed}_c} \frac{\tilde{P}_{j,t}}{\tilde{P}_{j,t-1}} \right)^{\frac{\Delta t}{N_{c,\text{obs}}}} = P_{i,t-\Delta t} \times \left(R_{c,t}\right)^{\Delta t}$$

where $\Delta t \in [1, 7]$ days and $R_{c,t}$ represents the daily geometric mean movement of active items in the same COICOP class. Beyond 7 consecutive days of missing observations, items are classified as structural exits and excluded from the active basket.

> **Prohibition:** Static carry-forward imputation ($\widehat{P}_{i,t} = P_{i,t-1}$) is **strictly avoided** as it dampens measured inflation volatility and creates severe downward lag bias during inflationary shocks. Multi-day gaps are geometrically compounded by $(\cdot)^{\Delta t}$ to accurately reflect price drift across missing days.

#### 2. Jevons Elementary Price Index (Chapter 8, §8.15)
For each unique canonical item $i$ relative to its base period price $\tilde{P}_{i,0}$:

$$I_i^{t/0} = \left( \frac{\tilde{P}_{i,t}}{\tilde{P}_{i,0}} \right) \times 100.0$$

Aggregated across $N_c$ items within COICOP subclass $c$:

$$I_c^{t/0} = \prod_{i=1}^{N_c} \left( \frac{\tilde{P}_{i,t}}{\tilde{P}_{i,0}} \right)^{\frac{1}{N_c}} \times 100.0 = \exp\left( \frac{1}{N_c} \sum_{i=1}^{N_c} \ln \left(\frac{\tilde{P}_{i,t}}{\tilde{P}_{i,0}}\right) \right) \times 100.0$$

* **Axiomatic Guarantees:**
  * **Time Reversal Test:** $I^{t/0} \times I^{0/t} = 1.0$ (Satisfied)
  * **Transitivity:** $I^{0:t} = I^{0:k} \times I^{k:t}$ (Satisfied)
  * **Chain Drift:** **Zero** (Geometric formulation is completely immune to promotional price bouncing).

---

### Tier 3: Intra-Division Subclass Aggregation

Subclasses ($c$) are combined into Division indices ($I_d^{t/0}$) using intra-division expenditure weights $w_{c \mid d}$ derived from the CSES survey:

$$I_{\text{Division } d}^{t/0} = \sum_{c \in \text{Division } d} w_{c \mid d} \cdot I_c^{t/0}$$

$$\text{where } \sum_{c \in \text{Division } d} w_{c \mid d} = 1.000 \quad (100.0\%)$$

---

### Tier 4 & 5: National Headline & Core CPI Aggregation

Using official NIS Cambodia plutocratic 12-Division weights ($W_d$):

$$CPI_{\text{Headline}}^t = \frac{\sum_{d=1}^{12} W_d \cdot I_d^{t/0}}{\sum_{d \in \text{active}} W_d}$$

#### Official NIS Cambodia 12-Division Expenditure Weights ($W_d$):
| Division | Description | National Weight ($W_d$) | In Headline? | In Core CPI? |
| :---: | :--- | :---: | :---: | :---: |
| **01** | Food and Non-Alcoholic Beverages | **44.800%** | Yes | ❌ Excluded |
| **02** | Alcoholic Beverages & Tobacco | **1.500%** | Yes | Yes |
| **03** | Clothing and Footwear | **2.900%** | Yes | Yes |
| **04** | Housing, Water, Electricity, Gas & Fuels | **17.100%** | Yes | ❌ Excluded |
| **05** | Furnishings & Household Maintenance | **3.300%** | Yes | Yes |
| **06** | Health & Pharmaceuticals | **5.600%** | Yes | Yes |
| **07** | Transport & Automotive Fuels | **12.200%** | Yes | ❌ Excluded |
| **08** | Communication & Telecom | **3.900%** | Yes | Yes |
| **09** | Recreation and Culture | **1.900%** | Yes | Yes |
| **10** | Education | **1.500%** | Yes | Yes |
| **11** | Restaurants and Hotels | **3.100%** | Yes | Yes |
| **12** | Miscellaneous Goods & Services | **2.200%** | Yes | Yes |
| **Total** | **National CPI Basket** | **100.000%** | **100.000%** | **25.900% (Normalized to 100%)** |

#### Core CPI Formulation (Exclusion Method):
$$CPI_{\text{Core}}^t = \frac{\sum_{d \notin \{01, 04, 07\}} W_d \cdot I_d^{t/0}}{\sum_{d \notin \{01, 04, 07\}} W_d}$$

---

## 3. Weight Updating & Continuity (Annual Double-Overlap Linking)

When updating the expenditure basket or rebasing:
* **One-Month Overlap Technique (Chapter 9, §9.35):**
  $$I_{\text{Linked}}^{0:t} = I_{\text{Old}}^{0:T} \times \frac{I_{\text{New}}^{T:t}}{100.0}$$
  where $T$ is the overlap link month (December). This preserves historical continuity without step jumps.

---

## 4. Methodological Evaluation Matrix

| Metric / Requirement | Carli Formula | Dutot Formula | Chained Laspeyres | Two-Tier Lowe-Jevons *(Adopted)* |
| :--- | :---: | :---: | :---: | :---: |
| **Axiomatic Consistency** | ❌ Fails Time Reversal | ⚠️ Scale Sensitive | ❌ Suffers from Chain Drift | ✅ **Fully Satisfied** |
| **E-Commerce Price Bouncing** | ❌ Severe Upward Bias (+3%) | ⚠️ Biased by Luxury Items | ❌ Drifts over time | ✅ **Zero Chain Drift** |
| **Quantity Data Requirement** | None | None | Needs $Q_{i,t}$ per store | ✅ **None at Item Level** |
| **IMF / ILO Manual 2020 Compliance** | ❌ Discouraged | ⚠️ Restricted use | ⚠️ Requires scanner data | ✅ **Recommended Standard** |
| **Alignment with NIS Cambodia** | ❌ No | ❌ No | ❌ Incompatible | ✅ **Exact Alignment** |

---

## 5. Summary of Pipeline Advantages

1. **Rigorously Justified:** Fully backed by Chapters 3, 5, 6, 8, and 10 of the *2020 CPI Manual*.
2. **Engineered for Web Scraping:** Tolerates catalog churn, product additions/removals, and volatile promotional sales.
3. **Reproducible & Transparent:** Decouples physical package parsing, missing imputation, micro geometric averaging, and macro plutocratic aggregation into modular dbt/Python stages.
