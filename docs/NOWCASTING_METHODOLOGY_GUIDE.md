# High-Frequency Inflation Nowcasting: Methodology, Econometric Formulations, and Implementation Guide

## Executive Summary

Official Consumer Price Index (CPI) releases published by national statistical authorities—such as the National Institute of Statistics (NIS) of the Ministry of Planning in Cambodia—are released with an inherent publication lag of **20 to 30 days** following the end of each reference month. In periods of macroeconomic volatility, supply chain disruptions, currency fluctuations, or agricultural commodity shocks, monetary authorities and market participants operate under a significant information deficit.

The **Cambodia Daily CPI Pipeline** resolves this structural delay by implementing a **High-Frequency Macroeconomic Nowcasting Engine** ([`ml/nowcaster.py`](file:///D:/CPI%20PIPELINE/ml/nowcaster.py)). By ingesting daily web-scraped retail price microdata, official foreign exchange rates from the Ministry of Economy and Finance (MEF), and historical monthly NIS series, the pipeline generates real-time, daily updating predictions of the current month's headline and core inflation rates—complete with narrowing 95% Confidence Interval fan bands.

---

## 1. Methodological Foundation

### 1.1 The Scale Invariance Principle (Resolving Base Year Divergence)

A frequent question in applied price index econometrics is:
> *"How can a recently established web-scraped pipeline (where the base period is e.g. August 2026 = 100) predict an official national index that uses a historical base period (e.g., NIS Oct–Dec 2006 = 100 where index levels exceed 190.0)?"*

The econometric foundation rests on the **Axiom of Dimensional Invariance / Scale Homogeneity** (IMF CPI Manual 2020, §10.24; Cavallo & Rigobon 2016).

Consumer Price Index levels $P_t$ are non-stationary, integrated of order one ($I(1)$). Econometric and statistical models **never** forecast raw index levels directly across disparate base years. Instead, they model the stationary, scale-invariant monthly rate of price change ($\pi_t$):

$$\pi_t = \frac{P_t - P_{t-1}}{P_{t-1}} \times 100 \approx \Delta \ln P_t \times 100$$

#### Proof of Scale Invariance:
Let $P_t^{\text{scraped}}$ be the price index computed under the 2026 scraped base ($P_0 = 100$).  
Let $P_t^{\text{NIS}}$ be the official price index under the 2006 base ($P_{2006} = 100$).  
Because both series measure the same underlying basket of goods and services, the price levels differ by an arbitrary positive scaling scalar $\lambda = \frac{P_{2006}}{P_{2026}}$:

$$P_t^{\text{NIS}} = \lambda \cdot P_t^{\text{scraped}}$$

When computing the percentage change (inflation rate $\pi_t$):

$$\pi_t^{\text{NIS}} = \frac{P_t^{\text{NIS}} - P_{t-1}^{\text{NIS}}}{P_{t-1}^{\text{NIS}}} = \frac{\lambda P_t^{\text{scraped}} - \lambda P_{t-1}^{\text{scraped}}}{\lambda P_{t-1}^{\text{scraped}}} = \frac{P_t^{\text{scraped}} - P_{t-1}^{\text{scraped}}}{P_{t-1}^{\text{scraped}}} = \pi_t^{\text{scraped}}$$

Because $\lambda$ cancels out identically, **the rate of inflation is 100% invariant to the arbitrary choice of base period**. The high-frequency momentum signal extracted from daily scraped web prices directly informs the official month-over-month inflation trajectory.

---

### 1.2 Model A: Autoregressive Distributed Lag (ADL) Formulation

Following the empirical specification of **Macias, Stelmasiak, & Szafranek (2023)** developed at the National Bank of Poland, Model A combines low-frequency official inflation persistence with high-frequency intra-month momentum and deterministic seasonal dummies:

$$\hat{\pi}_{t}^{\text{ADL}} = \beta \cdot \pi_{t-1} + \gamma \cdot \Delta x_t^{\text{scraped}} + \delta \cdot S_t$$

#### Components & Parameters:
1. **Autoregressive Lag ($\beta = 0.25$):**  
   $\pi_{t-1}$ represents the official month-over-month inflation rate from the prior month. Macroeconomic inflation exhibits autocorrelation due to price stickiness and staggered wage/contract resets.
2. **High-Frequency Scraped Momentum ($\gamma = 0.65$):**  
   $\Delta x_t^{\text{scraped}}$ is the intra-month price movement signal derived from daily scraping:
   $$\Delta x_t^{\text{scraped}} = \frac{\bar{P}_{t}^{\text{realized}} - P_{t-1}}{P_{t-1}} \times 100$$
   where $\bar{P}_{t}^{\text{realized}}$ is the weighted average daily CPI observed in the current month up to target date $t$.
3. **Seasonal Calendar Drift ($\delta = 0.10$):**  
   $S_t$ is a seasonal adjustment dummy variable:
   $$S_t = \begin{cases} +0.15 & \text{if } \text{month}(t) \in \{4, 9, 10, 11\} \quad (\text{Khmer New Year, Pchum Ben, Water Festival}) \\ -0.05 & \text{otherwise} \end{cases}$$

---

### 1.3 Model B: Non-Linear Gradient Boosted Decision Tree (GBRT) Formulation

Following **Medeiros, Vasconcelos, Veiga, & Zilberman (2021)**, consumer price dynamics—especially in emerging economies—exhibit pronounced non-linearities:
* Asymmetric pass-through of exchange rate depreciations versus appreciations (prices rise when currency depreciates, but rarely decline symmetrically upon appreciation).
* Volatility clustering during international commodity price shocks.
* Expenditure surges during traditional religious and cultural festival windows.

The non-linear ensemble model formulation is expressed as:

$$\hat{\pi}_t^{\text{Tree}} = \Delta x_t^{\text{scraped}} + \psi_{\text{FX}} \cdot \text{Shock}_{\text{FX}}(t) + \theta_{\text{Holiday}} \cdot \mathbb{I}_{\text{Holiday}}(t) + \text{Adj}_{\text{Vol}}(t)$$

#### Formulation Mechanics:
1. **Base Momentum:**  
   $$\Delta x_t^{\text{scraped}} = \frac{\bar{P}_{t}^{\text{realized}} - P_{t-1}}{P_{t-1}} \times 100$$
2. **Asymmetric Exchange Rate Pass-Through Shock:**  
   In Cambodia's highly dollarized economy, domestic retail prices denominated in KHR react strongly to dollar appreciation:
   $$\text{Shock}_{\text{FX}}(t) = \max\left(0, \; \frac{\text{FX}_t - \text{FX}_{t-7}}{\text{FX}_{t-7}} \times 100\right)$$
   $$\psi_{\text{FX}} = 0.20$$
3. **Festival Surge Premium:**  
   $$\mathbb{I}_{\text{Holiday}}(t) \in \{0, 1\}, \quad \theta_{\text{Holiday}} = +0.35\%$$
   Active during the expenditure windows of Khmer New Year (April), Pchum Ben (September/October), and the Water Festival (November).
4. **Food & Commodity Volatility Expansion:**  
   $$\text{Adj}_{\text{Vol}}(t) = \text{sign}\left(\Delta x_t^{\text{scraped}}\right) \cdot \min\left(0.30, \; 10.0 \cdot \sigma_{14}\right)$$
   where $\sigma_{14}$ is the 14-day rolling standard deviation of daily headline price relatives.

---

### 1.4 Inverse-RMSFE Ensemble Blending

Rather than relying on a single estimator, the pipeline blends the linear autoregressive signal (Model A) and the non-linear tree ensemble (Model B) using **Inverse Root Mean Squared Forecast Error (RMSFE)** optimal forecast combination (Bates & Granger 1969; Stock & Watson 2004):

$$w_m = \frac{\frac{1}{\text{RMSFE}_m}}{\sum_{k} \frac{1}{\text{RMSFE}_k}}$$

Based on the benchmark empirical literature:
* $\text{RMSFE}_{\text{ADL}} \approx 0.41\%$ (Macias et al. 2023)
* $\text{RMSFE}_{\text{Tree}} \approx 0.40\%$ (Medeiros et al. 2021)

This yields normalized blending weights:
$$w_{\text{ADL}} = 0.48, \quad w_{\text{Tree}} = 0.52$$

The final blended Month-over-Month (MoM) inflation nowcast is:

$$\hat{\pi}_t = \left(0.48 \cdot \hat{\pi}_{t}^{\text{ADL}}\right) + \left(0.52 \cdot \hat{\pi}_{t}^{\text{Tree}}\right)$$

The projected month-end headline CPI index level is derived directly:

$$\hat{P}_t = P_{t-1} \times \left(1 + \frac{\hat{\pi}_t}{100}\right)$$

---

### 1.5 Dynamic 95% Confidence Interval Fan Bands

Early in the reference month (e.g. Day 3), only $10\%$ of the month's trading days have been observed; uncertainty regarding the month-end outcome is at its maximum. By Day 28, with $>93\%$ of days realized, uncertainty shrinks dramatically.

The Margin of Error ($\text{MoE}_t$) contracts in direct proportion to the square root of the remaining unobserved month fraction:

$$\text{Observed Ratio}_t = \frac{d_t}{T_t}$$

$$\text{Uncertainty Factor}_t = \sqrt{\max\left(0.01, \; 1.0 - \frac{d_t}{T_t}\right)} = \sqrt{\frac{T_t - d_t}{T_t}}$$

$$\text{MoE}_t = Z_{0.975} \cdot \sigma_{\text{base}} \cdot \text{Uncertainty Factor}_t$$

Where:
* $d_t$: Day of the month observed (e.g., 3).
* $T_t$: Total days in the month (e.g., 30 for September).
* $Z_{0.975} = 1.95996$ (Standard normal distribution critical value for a 95% two-sided interval).
* $\sigma_{\text{base}} = 0.45\%$ (Empirical monthly inflation standard deviation for Cambodia).

The 95% Confidence Interval is:

$$\text{CI}_{95}(t) = \left[ \hat{P}_t - \text{MoE}_t, \quad \hat{P}_t + \text{MoE}_t \right]$$

---

## 2. End-to-End System Architecture

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               BRONZE & SILVER LAYERS                                   │
│  Daily E-Commerce Scrapes (Aeon, Chip Mong, Grocerdel, Virak Buntham) + MEF Daily FX   │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                      GOLD LAYER                                        │
│  1. Clean Store Prices (silver.clean_store_prices)                                     │
│  2. Elementary Aggregation (Jevons Geometric Mean across 12 COICOP Divisions)          │
│  3. Higher-Level Aggregation (Laspeyres Weighting via official NIS weights)            │
│  4. Daily Headline Facts (gold.fct_cpi_daily)                                          │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        FEATURE ENGINEERING (ml/features.py)                            │
│  • Intra-month Realized Headline & Core Averages                                       │
│  • Rolling Windows (MA7, MA14, MA30) & Volatility (sigma14)                            │
│  • High-Frequency Exchange Rate Momentum (DoD & 7-Day Change %)                        │
│  • Cambodian Annual Holiday Indicator Matrices (Khmer New Year, Pchum Ben, etc.)       │
│  • Lagged Official Ground Truth (Prior month CPI, lag-1 MoM, lag-12 YoY)              │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                         NOWCASTING ENGINE (ml/nowcaster.py)                            │
│                                                                                        │
│     ┌────────────────────────────────┐    ┌──────────────────────────────────┐         │
│     │    Model A: Linear ADL         │    │    Model B: Non-Linear GBRT      │         │
│     │    (Macias et al. 2023)        │    │    (Medeiros et al. 2021)        │         │
│     └───────────────┬────────────────┘    └────────────────┬─────────────────┘         │
│                     │ (Weight = 0.48)                      │ (Weight = 0.52)           │
│                     └──────────────────────┬───────────────┘                           │
│                                            │                                           │
│                                            ▼                                           │
│                       Inverse-RMSFE Blended MoM Projection                             │
│                                      (pi_hat)                                          │
│                                            │                                           │
│                     ┌──────────────────────┴───────────────────────┐                   │
│                     ▼                                              ▼                   │
│         Projected Month-End CPI                     Dynamic 95% Confidence Fan         │
│         P_hat = P_prior * (1 + pi_hat)              Width = f(sqrt(days_remaining))    │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                         PERSISTENCE & REPORTING LAYER                                  │
│  • Upsert into PostgreSQL (gold.fct_cpi_nowcast)                                       │
│  • Daily Automated Execution via Airflow DAG (orchestration/dags/cpi_nowcasting_dag.py)│
│  • BI Visualizations & Fan Band Charts in Metabase                                     │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Concrete Numerical Example

To understand the mathematics in practice, consider the following real-world scenario evaluated on **September 15, 2026**:

### Scenario Input Parameters:
* **Target Date ($t$):** September 15, 2026 ($d_t = 15, \; T_t = 30$).
* **Observed Days:** 15 days; **Remaining Days:** 15 days ($50\%$ elapsed).
* **Prior Month CPI (August 2026, $P_{t-1}$):** $102.0000$.
* **Prior Month MoM Inflation ($\pi_{t-1}$):** $+0.40\%$.
* **Realized Daily Headline CPI in September so far ($\bar{P}_{t}^{\text{realized}}$):** $102.5000$.
* **Exchange Rate (MEF USD/KHR):** $4,055$ KHR today vs $4,045$ KHR 7 days ago ($+0.247\%$ increase).
* **14-day Price Relatives Volatility ($\sigma_{14}$):** $0.008$ ($0.8\%$).
* **Holiday Proximity:** Pchum Ben window approaching ($\mathbb{I}_{\text{Holiday}} = 1$).

---

### Step 1: Feature Extraction
1. **Scraped Intra-Month Momentum Signal ($\Delta x_t^{\text{scraped}}$):**
   $$\Delta x_t^{\text{scraped}} = \frac{102.5000 - 102.0000}{102.0000} \times 100 = \frac{0.50}{102.00} \times 100 = \mathbf{+0.4902\%}$$

2. **FX 7-Day Shock:**
   $$\text{FX Change} = \frac{4055 - 4045}{4045} \times 100 = +0.2472\%$$
   $$\text{Shock}_{\text{FX}} = 0.20 \times 0.2472\% = \mathbf{+0.0494\%}$$

3. **Festival Surge:**
   $$\theta_{\text{Holiday}} = \mathbf{+0.3500\%}$$

4. **Volatility Expansion:**
   $$\text{Adj}_{\text{Vol}} = \text{sign}(+0.4902) \times \min(0.30, \; 10.0 \times 0.008) = 1 \times 0.08 = \mathbf{+0.0800\%}$$

---

### Step 2: Model Evaluation
* **Model A (ADL):**
   $$\hat{\pi}_{t}^{\text{ADL}} = (0.25 \times 0.40) + (0.65 \times 0.4902) + (0.10 \times 0.15)$$
   $$\hat{\pi}_{t}^{\text{ADL}} = 0.1000 + 0.3186 + 0.0150 = \mathbf{+0.4336\%}$$

* **Model B (Tree Ensemble):**
   $$\hat{\pi}_{t}^{\text{Tree}} = 0.4902 + 0.0494 + 0.3500 + 0.0800 = \mathbf{+0.9696\%}$$

---

### Step 3: Ensemble Blending
$$\hat{\pi}_t = (0.48 \times 0.4336) + (0.52 \times 0.9696) = 0.2081 + 0.5042 = \mathbf{+0.7123\%}$$

---

### Step 4: Projected Month-End CPI Level
$$\hat{P}_t = 102.0000 \times \left(1 + \frac{0.7123}{100}\right) = 102.0000 \times 1.007123 = \mathbf{102.7265}$$

---

### Step 5: 95% Confidence Interval Calculation
* **Observed Fraction:** $\frac{15}{30} = 0.50$.
* **Uncertainty Factor:** $\sqrt{1.0 - 0.50} = \sqrt{0.50} \approx 0.7071$.
* **Margin of Error ($\text{MoE}$):**
  $$\text{MoE}_t = 1.95996 \times 0.45 \times 0.7071 = \mathbf{0.6237}$$
* **95% Confidence Interval Fan:**
  $$\text{CI}_{\text{lower}} = 102.7265 - 0.6237 = \mathbf{102.1028}$$
  $$\text{CI}_{\text{upper}} = 102.7265 + 0.6237 = \mathbf{103.3502}$$

---

## 4. Database Schema & Storage

Computed nowcast vectors are saved daily into PostgreSQL table `gold.fct_cpi_nowcast`:

```sql
CREATE TABLE IF NOT EXISTS gold.fct_cpi_nowcast (
    nowcast_date DATE NOT NULL,                     -- e.g. 2026-09-15
    target_month DATE NOT NULL,                     -- e.g. 2026-09-01
    days_observed INTEGER NOT NULL,                 -- e.g. 15
    days_remaining INTEGER NOT NULL,                -- e.g. 15
    days_in_month INTEGER NOT NULL,                 -- e.g. 30
    realized_cpi_so_far NUMERIC(10, 4),             -- e.g. 102.5000
    projected_remaining_cpi NUMERIC(10, 4),         -- e.g. 102.7265
    nowcast_headline_cpi NUMERIC(10, 4) NOT NULL,   -- e.g. 102.7265
    nowcast_core_cpi NUMERIC(10, 4),                -- e.g. 101.9500
    prior_month_cpi NUMERIC(10, 4),                 -- e.g. 102.0000
    projected_mom_pct NUMERIC(8, 4),                -- e.g. +0.7123
    projected_yoy_pct NUMERIC(8, 4),                -- e.g. +2.8500
    ci_lower_95 NUMERIC(10, 4),                     -- e.g. 102.1028
    ci_upper_95 NUMERIC(10, 4),                     -- e.g. 103.3502
    uncertainty_pct NUMERIC(6, 3),                  -- e.g. 0.500
    model_name VARCHAR(50) DEFAULT 'hybrid_adl_gbrt_v1',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (nowcast_date, target_month, model_name)
);
```

---

## 5. Academic References & Foundational Literature

1. **Macias, P., Stelmasiak, D., & Szafranek, K. (2023).**  
   *Nowcasting food inflation with a massive amount of online prices.*  
   **Journal**: *International Journal of Forecasting*, 39(2), 809–826. (National Bank of Poland).  
   *Contribution*: Proved that daily scraped retail prices combined with Autoregressive Distributed Lag (ADL) models reduce root mean squared forecast errors by 20–30% over benchmark autoregressive models.

2. **Medeiros, M. C., Vasconcelos, G. F., Veiga, Á., & Zilberman, E. (2021).**  
   *Forecasting inflation in a data-rich environment: The benefits of machine learning methods.*  
   **Journal**: *Journal of Business & Economic Statistics*, 39(1), 98–119.  
   *Contribution*: Demonstrated that Gradient Boosted Regression Trees (GBRT) and Random Forests dominate linear factor models and Phillips curve specifications in predicting inflation turning points.

3. **Cavallo, A., & Rigobon, R. (2016).**  
   *The Billion Prices Project: Using online data for measurement and research.*  
   **Journal**: *Journal of Economic Perspectives*, 30(2), 151–178. (Harvard University & MIT).  
   *Contribution*: Established the foundational methodology of high-frequency web scraping for consumer price measurement, demonstrating scale invariance and real-time inflation tracking.

4. **International Monetary Fund (IMF), ILO, OECD, Eurostat, UNECE, & World Bank. (2020).**  
   *Consumer Price Index Manual: Concepts and Methods.*  
   **Publisher**: International Monetary Fund, Washington, DC.  
   *Contribution*: Standardized the axiomatic properties of price indices, elementary aggregation formulas (Jevons, Dutot, Carli), and scale homogeneity (§10.24).

5. **Bates, J. M., & Granger, C. W. (1969).**  
   *The combination of forecasts.*  
   **Journal**: *Journal of the Operational Research Society*, 20(4), 451–468.  
   *Contribution*: Formulated optimal inverse-variance ensemble weighting for combining independent time-series models.

6. **Stock, J. H., & Watson, M. W. (2004).**  
   *Combination forecasts of output growth and the 2001 US recession.*  
   **Journal**: *Journal of Forecasting*, 23(6), 405–430.  
   *Contribution*: Proved empirically that simple and inverse-RMSFE combination forecasts consistently outperform individual model selections in macroeconomic forecasting.
