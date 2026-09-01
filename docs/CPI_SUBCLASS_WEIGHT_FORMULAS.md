# Mathematical Formulas for Subclass & Elementary Aggregate Weights in CPI

**Document Reference:** Technical Reference on Weighting Mathematics  
**Standard Compliance:** IMF / ILO / OECD / Eurostat / UN / World Bank *Consumer Price Index Manual: Concepts and Methods (2020)*  
**Primary Chapters:** Chapter 3 (*Expenditure Weights and Their Sources*) & Chapter 8 (*Calculating Consumer Price Indices in Practice*)

---

## 1. Overview of Weighting Terminology in the CPI Manual

The CPI Manual distinguishes between three critical reference periods:
* **$b$ (Weight Reference Period):** The period during which the Household Budget Survey (HBS / CSES) data was collected (usually a 12-month calendar year).
* **$0$ (Price Reference Period):** The base period whose prices serve as the denominator in price comparisons (often December of year $b$ or a subsequent year).
* **$t$ (Current Period):** The active observation period (day, month, quarter).

---

## 2. Base Expenditure Share Formula (Survey Period $b$)

From **Chapter 3 (§3.21–§3.32)** and **Chapter 8 (§8.100–§8.104)**, the nominal expenditure share of subclass $j$ in survey period $b$ across $K$ categories is:

$$w_j^b = \frac{e_j^b}{\sum_{k=1}^{K} e_k^b} = \frac{p_j^b q_j^b}{\sum_{k=1}^{K} p_k^b q_k^b}$$

Where:
* $e_j^b = p_j^b q_j^b$ is the aggregate expenditure on subclass $j$ across surveyed households during period $b$.
* $\sum_{k=1}^K e_k^b$ is the total expenditure across all $K$ items within the aggregation scope (e.g. within a COICOP division or nationally).
* $\sum_{j=1}^K w_j^b = 1.000$ (or $100.0\%$).

---

## 3. The Price-Updated Weight Formula (**Lowe Index — Equation 8.15**)

When statistical agencies maintain fixed physical quantities ($q_j^b$) from the survey period but align weights to base-period prices $p_j^0$, the **hybrid price-updated weight** $w_j^{b(0)}$ is computed as:

$$w_j^{b(0)} = \frac{w_j^b \left(\frac{p_j^0}{p_j^b}\right)}{\sum_{k=1}^{K} w_k^b \left(\frac{p_k^0}{p_k^b}\right)} = \frac{p_j^0 q_j^b}{\sum_{k=1}^{K} p_k^0 q_k^b}$$

Where:
* $\frac{p_j^0}{p_j^b}$ is the price relative (inflation adjustment factor) for subclass $j$ from survey period $b$ to base period $0$.
* The resulting **Lowe Index** formula is:
  $$I_{\text{Lowe}}^{0:t} = \sum_{j=1}^{K} w_j^{b(0)} \cdot I_j^{0:t} = \frac{\sum_{j=1}^{K} p_j^t q_j^b}{\sum_{k=1}^{K} p_k^0 q_k^b}$$

---

## 4. The Unadjusted Fixed Expenditure Weight Formula (**Young Index — Equation 8.14**)

When compilers assume consumers adjust consumption to maintain constant spending proportions (elasticity of substitution $\approx 1$):

$$I_{\text{Young}}^{0:t} = \sum_{j=1}^{K} w_j^b \cdot I_j^{0:t}$$

Where the survey expenditure share $w_j^b$ is used directly without price-updating.

---

## 5. Intra-Division vs. National Weight Disaggregation

In hierarchical COICOP classifications (e.g. Division $\to$ Group $\to$ Class $\to$ Subclass):

### 5.1 Intra-Division Subclass Weight ($w_{c \mid d}$)
The relative share of subclass $c$ within its parent division $d$:

$$w_{c \mid d}^b = \frac{e_c^b}{e_d^b} = \frac{\sum_{h=1}^H e_{h, c}^b}{\sum_{h=1}^H e_{h, d}^b}$$

$$\text{Subject to: } \sum_{c \in \text{Division } d} w_{c \mid d}^b = 1.000 \quad (100.0\%)$$

### 5.2 National Total Subclass Weight ($W_c$)
The national expenditure share of subclass $c$ across all 12 COICOP divisions:

$$W_c^b = \frac{e_c^b}{\sum_{d=1}^{12} e_d^b} = W_d^b \times w_{c \mid d}^b$$

---

## 6. Regional & Outlet Stratification (**Chapter 3, Table 3.2 & Equation 8.27**)

When a national subclass weight is disaggregated across geographical regions ($r$) or outlet channels ($s$):

$$w_{j, r}^b = w_j^b \times s_{j, r}^b = w_j^b \times \left( \frac{e_{j, r}^b}{e_j^b} \right)$$

Where:
* $s_{j, r}^b$ is the proportion of total subclass $j$ expenditure spent in region $r$.
* $\sum_{r} w_{j, r}^b = w_j^b$.

---

## 7. Mathematical Summary Table

| Index / Weight Concept | Mathematical Formula | Manual Reference | Primary Use Case |
| :--- | :---: | :---: | :--- |
| **Survey Expenditure Share** | $w_j^b = \frac{p_j^b q_j^b}{\sum p_k^b q_k^b}$ | Chapter 3 (§3.21) | Raw HBS / CSES survey weights |
| **Young Index** | $I_Y^{0:t} = \sum w_j^b \left(\frac{p_j^t}{p_j^0}\right)$ | Chapter 8 (Eq. 8.14) | Aggregation when expenditure shares remain stable |
| **Price-Updated Weight (Lowe)** | $w_j^{b(0)} = \frac{w_j^b (p_j^0 / p_j^b)}{\sum w_k^b (p_k^0 / p_k^b)}$ | Chapter 8 (Eq. 8.15) | Standard national CPI aggregation |
| **Geometric Young Index** | $I_{GY}^{0:t} = \prod \left(\frac{p_j^t}{p_j^0}\right)^{w_j^b}$ | Chapter 8 (Eq. 8.19) | Subclass aggregation under Cobb-Douglas preferences |
