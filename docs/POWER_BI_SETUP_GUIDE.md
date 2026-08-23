# Power BI Setup & Interactive Dashboard Guide

This guide details how to connect **Microsoft Power BI Desktop** directly to your **Cambodia CPI PostgreSQL Data Warehouse** to build executive inflation dashboards.

---

## 1. PostgreSQL Connection Settings

In Power BI Desktop:
1. Click **Get Data** $\to$ **PostgreSQL database** $\to$ **Connect**.
2. Enter the connection parameters:
   * **Server:** `localhost:5432`
   * **Database:** `cpi_db`
   * **Data Connectivity mode:** `Import` (or `DirectQuery` for real-time live queries)
3. Enter credentials:
   * **User name:** `cpi_user`
   * **Password:** `cpi_pass`

---

## 2. Recommended Data Model (Star Schema)

Select and load the following tables from `gold` and `silver` schemas:

```
                          ┌────────────────────────┐
                          │   silver.dim_items     │ (Item Dimension)
                          │   - item_id (PK)       │
                          │   - canonical_name     │
                          │   - brand              │
                          │   - size_norm          │
                          └───────────┬────────────┘
                                      │ 1
                                      │
                                      │ *
┌─────────────────────────┐  ┌────────┴───────────────┐  ┌─────────────────────────┐
│   gold.coicop_weights   │  │ gold.fct_daily_price_  │  │ gold.cpi_headline_daily │
│   - coicop_division(PK) │  │   stats (Jevons Facts) │  │ (National Daily Indices)│
│   - division_name       │  │ - scrape_date          │  │ - scrape_date           │
│   - weight_pct          │  │ - item_id (FK)         │  │ - formula               │
└───────────┬─────────────┘  │ - coicop_division (FK) │  │ - index_value (CPI)     │
            │ 1              │ - p_khr_jevons         │  │ - divisions_present     │
            │                │ - base_price_khr       │  └─────────────────────────┘
            │ *              │ - jevons_index_base    │
┌───────────┴─────────────┐  └────────────────────────┘  ┌─────────────────────────┐
│ gold.cpi_category_daily │                              │ gold.cpi_fisher_        │
│ (12 Division Indices)   │                              │   superlative           │
│ - scrape_date           │                              │ - scrape_date           │
│ - coicop_division (FK)  │                              │ - fisher_index          │
│ - index_value           │                              │ - substitution_bias_pct │
└─────────────────────────┘                              └─────────────────────────┘
```

---

## 3. Essential DAX Measures

Create a dedicated **Measures Table** in Power BI and add the following DAX calculations:

### 1. Headline CPI
```dax
Headline_CPI = 
CALCULATE(
    MAX(gold_cpi_headline_daily[index_value]),
    gold_cpi_headline_daily[formula] = "Laspeyres"
)
```

### 2. Day-on-Day (DoD) Inflation Rate (%)
```dax
DoD_Inflation_Pct = 
VAR CurrentDate = MAX(gold_cpi_headline_daily[scrape_date])
VAR CurrentCPI = [Headline_CPI]
VAR PrevCPI = 
    CALCULATE(
        [Headline_CPI],
        gold_cpi_headline_daily[scrape_date] = CurrentDate - 1
    )
RETURN
    IF(
        NOT ISBLANK(PrevCPI) && PrevCPI > 0,
        DIVIDE(CurrentCPI - PrevCPI, PrevCPI) * 100,
        BLANK()
    )
```

### 3. Month-on-Month (MoM) Inflation Rate (%)
```dax
MoM_Inflation_Pct = 
VAR CurrentDate = MAX(gold_cpi_headline_daily[scrape_date])
VAR CurrentCPI = [Headline_CPI]
VAR PrevMonthCPI = 
    CALCULATE(
        [Headline_CPI],
        gold_cpi_headline_daily[scrape_date] = EDATE(CurrentDate, -1)
    )
RETURN
    IF(
        NOT ISBLANK(PrevMonthCPI) && PrevMonthCPI > 0,
        DIVIDE(CurrentCPI - PrevMonthCPI, PrevMonthCPI) * 100,
        BLANK()
    )
```

### 4. Consumer Substitution Bias (%)
```dax
Substitution_Bias_Pct = 
MAX(gold_cpi_fisher_superlative[substitution_bias_pct])
```

---

## 4. Recommended Power BI Dashboard Layout (3 Pages)

### Page 1: Executive Macroeconomic Overview
* **KPI Cards:** Latest Headline CPI (`100.00`), MoM Inflation Rate (`+0.42%`), DoD Inflation Rate (`+0.03%`).
* **Main Visual:** Line Chart of Daily National Headline CPI (Laspeyres vs GEKS-Törnqvist vs Fisher Superlative).
* **Division Treemap:** 12 COICOP Divisions sized by official Cambodia NIS weight ($w_i\%$) and colored by monthly inflation rate.

### Page 2: 12 COICOP Division Deep-Dive
* **Slicer:** Division Selector (`01 - Food & Non-Alcoholic Beverages`, `04 - Housing & Utilities`, `07 - Transport`, etc.).
* **Area Chart:** Cumulative Division Price Index ($P_t / P_0 \times 100$) over time.
* **Top Inflation Contributors Table:** Top 10 items with highest weighted contribution to division inflation.

### Page 3: Item-Level Price Explorer & Superlative Analytics
* **Search / Filter:** Search by Product Name, Store (`AEON`, `Delishop`, `Samnang Shop`), or Brand.
* **Price History Chart:** Individual item unit price in KHR ($P_{\text{KHR}}$) over time.
* **Substitution Bias Gauge:** Quantified gap between fixed-basket Laspeyres and superlative Fisher index.
