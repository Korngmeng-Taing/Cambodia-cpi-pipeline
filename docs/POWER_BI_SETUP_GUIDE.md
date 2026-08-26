# Power BI Setup & Interactive Dashboard Guide

> **[!WARNING]**
> **IMPLEMENTATION STATUS (2026-08):** The Gold-layer index computation described in parts of this document - Jevons elementary aggregates, imputation, Laspeyres category/headline roll-ups, GEKS-Tornqvist, Fisher Ideal - is **planned but NOT implemented yet**. Its calculators, dbt models, and gold tables were removed from the codebase.
> Currently live: Bronze ingestion; Silver cleaning / item matching / AI classification / hedonic adjustment; Gold star schema (dim_items, dim_stores, fct_daily_prices); monitoring views. See README "Implementation Status".

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

Select and load the conformed star schema from the `gold` schema:

```
                          ┌────────────────────────┐
                          │     gold.dim_stores    │ (Store Dimension)
                          │   - store_slug (PK)    │
                          │   - store_name         │
                          │   - source_type        │
                          └───────────┬────────────┘
                                      │ 1
                                      │
                                      │ *
┌─────────────────────────┐     ┌─────┴──────────────────┐
│     gold.dim_items      │1   *│ gold.fct_daily_prices  │ (Clean Daily Price Facts)
│   - item_id (PK)        ├─────┤ - scrape_date          │
│   - canonical_name      │     │ - store_slug (FK)      │
│   - brand               │     │ - item_id (FK)         │
│   - coicop_division     │     │ - price_khr            │
│   - size_norm           │     │ - original_price_khr   │
└─────────────────────────┘     │ - discount_pct         │
                                │ - on_promo             │
                                │ - unit_price_khr       │
                                │ - cpi_eligible         │
                                │ - is_outlier           │
                                └────────────────────────┘
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
