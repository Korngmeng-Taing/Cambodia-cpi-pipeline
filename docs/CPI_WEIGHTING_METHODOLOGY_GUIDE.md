# CPI Weighting Methodology Guide: From Scraped Item to National Basket

**Document Version:** 1.0.0  
**Pipeline Compliance:** UN COICOP (2018), ILO Consumer Price Index Manual (2020), NIS Cambodia (CSES) Standards  
**Target Audience:** Economists, Data Engineers, Policy Analysts, Students  

---

## 1. Executive Overview

A common question in price index compilation is: **"How do we know how much weight each item gets?"**

In the Cambodia Daily Consumer Price Index (CPI) pipeline, weighting follows a **two-stage hybrid approach**:
1. **At the Individual Product / Brand Level:** Products are **equally weighted** using the unweighted **Jevons Geometric Mean Index** because daily supermarket scrapers do not provide store point-of-sale sales volume.
2. **At the Category & Division Level:** Categories and divisions are **unequally weighted** based on real empirical household spending shares from the **Cambodia Socio-Economic Survey (CSES)** published by the **National Institute of Statistics (NIS)**.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    5-TIER BOTTOM-UP AGGREGATION PYRAMID                         │
├─────────────────────────────────────────────────────────────────────────────────┤
│ Tier 5: National Headline CPI (100.000%)                                       │
│    ▲                                                                            │
│    │ Laspeyres Aggregation (12 Official NIS Division Weights, W_d)             │
│ Tier 4: 12 UN COICOP Divisions (e.g., Div 01 Food = 44.800%)                    │
│    ▲                                                                            │
│    │ Intra-Division Expenditure Weights (w_c|d)                                 │
│ Tier 3: 4-Digit COICOP Subclasses (e.g., 01.1.1 Rice & Cereals = 41.295% of Food)│
│    ▲                                                                            │
│    │ Jevons Geometric Mean (EQUAL WEIGHT per item: 1/N)                        │
│ Tier 2: Canonical Elementary Item Indices (I_i)                                 │
│    ▲                                                                            │
│    │ Unit Price Standardization (Price / Package Weight)                        │
│ Tier 1: Raw Multi-Store Daily Web Scrapes                                       │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. The Distinction: Equal Weight vs. Unequal Weight

| Level in Hierarchy | Example Entities | Weighting Strategy | Equal or Unequal? | Reason / Data Source |
| :--- | :--- | :--- | :---: | :--- |
| **Tier 1: Multi-Store Observations** | AEON price vs. DeliShop price for *Apsor Rice 5kg* | Geometric Average across stores | ✅ **Equal Weight** | No store-level sales volume available |
| **Tier 2: Item / Brand Level** | *Apsor Rice 5kg* vs. *CSM Rice 5kg* vs. *Buddha Rice 5kg* | Jevons Elementary Index ($1/N$) | ✅ **Equal Weight** | International standard for unweighted elementary aggregates (ILO 2020) |
| **Tier 3: Subclass Level** | *Rice & Cereals* (`01.1.1`) vs. *Coffee & Tea* (`01.2.1`) | Intra-Division Weight ($w_{c \mid d}$) | ❌ **Unequal Weight** | Households spend far more on rice than coffee (**NIS CSES Survey**) |
| **Tier 4: Division Level** | *Food* (`01`) vs. *Education* (`10`) | Official National Weight ($W_d$) | ❌ **Unequal Weight** | Food represents 44.8% of national spending, Education represents 1.5% |
| **Tier 5: National Level** | Headline CPI vs. Core CPI | Laspeyres Weighted Sum | ❌ **Unequal Weight** | Headline = 100%; Core excludes Food and Fuel |

---

## 3. Tier 1 & 2: Physical Package Weight & Item-Level Jevons Index

### 3.1 Physical Package Normalization
Different stores and brands package products in different quantities ($500\text{g}$, $5\text{kg}$, $50\text{kg}$, $330\text{ml}$, $1.5\text{L}$).  
To compare prices fairly, the Silver layer (`dbt/models/silver/intermediate/int_prices_cleaned.sql`) parses the physical weight using regular expressions:

```sql
-- Extract numeric value and unit from strings like "5kg", "500g"
(regexp_match(coalesce(raw.size_norm, ''), '([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]+)'))[1]::numeric AS size_value,
lower((regexp_match(coalesce(raw.size_norm, ''), '([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]+)'))[2]) AS size_unit
```

$$\text{Unit Price}_{\text{KHR}} = \begin{cases} 
\frac{\text{Price}_{\text{KHR}}}{\text{size\_value}} & \text{for kg, l} \\
\frac{\text{Price}_{\text{KHR}}}{\text{size\_value} / 1000} & \text{for g, ml} 
\end{cases}$$

### 3.2 Elementary Jevons Index (Equal Weight per Item)
For each unique canonical item $i$, its daily price relative to its base period price $P_{0,i}$ (anchored on August 18, 2026) is calculated:

$$I_i^{t/0} = \left( \frac{P_{i,t}}{P_{0,i}} \right) \times 100.0$$

Inside any subclass $c$ containing $N_c$ active items, each item is given **equal weight ($\frac{1}{N_c}$)**:

$$I_c^{t/0} = \exp\left( \frac{1}{N_c} \sum_{i=1}^{N_c} \ln I_i^{t/0} \right)$$

*Axiomatic Guarantee:* The Jevons formula satisfies the **Time Reversal Test** and **Transitivity**, avoiding the upward formula bias present in arithmetic averages (Carli index).

---

## 4. Tier 3: Intra-Division Subclass Weights ($w_{c \mid d}$)

### 4.1 What is "Intra-Division Weight"?
"Intra" means **inside**. The **Intra-Division Weight ($w_{c \mid d}$)** represents the percentage of spending allocated to a specific subclass **inside its own division only**, such that all subclasses within that division sum to **$100.000\%$**:

$$\sum_{c \in \text{Division } d} w_{c \mid d} = 100.000\%$$

### 4.2 How Intra-Division Weight is Calculated
From the national household expenditure survey:

$$w_{c \mid d} = \left( \frac{\text{Spending on Subclass } c}{\text{Total Spending on Division } d} \right) \times 100\% = \left( \frac{W_c}{W_d} \right) \times 100\%$$

### 4.3 Official Intra-Division Weights in This Project
Stored in [`dbt/seeds/cpi_basket_v1.csv`](file:///D:/CPI%20PIPELINE/dbt/seeds/cpi_basket_v1.csv):

#### Division 01: Food and Non-Alcoholic Beverages (100.000%)
| COICOP Code | Subclass Name | Intra-Division Weight ($w_{c \mid 01}$) | National Total Weight ($W_c$) |
| :---: | :--- | :---: | :---: |
| **`01.1.1`** | **Rice & Cereals** | **41.295%** | **18.500%** |
| **`01.1.2`** | **Meat & Poultry** | **22.768%** | **10.200%** |
| **`01.1.3`** | **Fish & Seafood** | **12.946%** | **5.800%** |
| **`01.1.7`** | **Vegetables** | **6.250%** | **2.800%** |
| **`01.1.4`** | **Milk, Cheese & Eggs** | **5.134%** | **2.300%** |
| **`01.1.6`** | **Fruit** | **4.688%** | **2.100%** |
| **`01.1.5`** | **Oils & Fats** | **3.125%** | **1.400%** |
| **`01.1.8`** | **Sugar & Confectionery** | **2.009%** | **0.900%** |
| **`01.1.9`** | **Food Products n.e.c.** | **0.893%** | **0.400%** |
| **`01.2.1`** | **Coffee, Tea & Cocoa** | **0.446%** | **0.200%** |
| **`01.2.2`** | **Mineral Waters & Soft Drinks** | **0.446%** | **0.200%** |
| **TOTAL** | **Division 01 Total** | **100.000%** | **44.800%** |

#### Other Key Division Subclass Breakdowns:
* **Division 02 (Alcohol & Tobacco):** Spirits & Beer (`66.667%`), Tobacco (`33.333%`).
* **Division 03 (Clothing & Footwear):** Garments (`68.966%`), Footwear (`20.690%`), Other Clothing (`10.345%`).
* **Division 04 (Housing & Utilities):** Actual Rentals (`70.175%`), Electricity EDC (`14.620%`), Water PPWSA (`10.526%`), LPG Gas (`4.678%`).
* **Division 06 (Health):** Pharmaceuticals (`75.000%`), Medical Devices (`25.000%`).
* **Division 07 (Transport):** Retail Fuel (`73.770%`), Passenger Transit (`26.230%`).
* **Division 08 (Communication):** Mobile Data / Internet (`61.538%`), Phone Equipment (`38.462%`).

---

## 5. Tier 4 & 5: National Division Weights ($W_d$) & National CPI

### 5.1 Where Do National Weights Come From?
National weights come from the **Cambodia Socio-Economic Survey (CSES)** conducted by the **National Institute of Statistics (NIS)**, Ministry of Planning.

Surveyors collect monthly consumption expenditure records across thousands of households in all 25 provinces. The **National Weight ($W_d$)** is the share of total household spending:

$$W_d = \left( \frac{\text{Total National Spending on Division } d}{\text{Total National Spending on ALL Goods and Services}} \right) \times 100\%$$

$$\sum_{d=1}^{12} W_d = 100.000\%$$

### 5.2 Official National 12-Division Weights
Stored in [`dbt/seeds/category_weights.csv`](file:///D:/CPI%20PIPELINE/dbt/seeds/category_weights.csv):

| Division Code | Division Name | Official NIS Weight ($W_d$) | Headline CPI | Core CPI |
| :---: | :--- | :---: | :---: | :---: |
| **`01`** | Food and non-alcoholic beverages | **44.775%** | Included | ❌ Excluded |
| **`02`** | Alcoholic beverages, tobacco & narcotics | **1.625%** | Included | Included |
| **`03`** | Clothing and footwear | **3.036%** | Included | Included |
| **`04`** | Housing, water, electricity, gas & fuels | **17.084%** | Included | ❌ Excluded (Fuels) |
| **`05`** | Furnishings & routine household maintenance | **3.325%** | Included | Included |
| **`06`** | Health | **5.589%** | Included | Included |
| **`07`** | Transport | **12.228%** | Included | ❌ Excluded (Fuel) |
| **`08`** | Communication | **3.921%** | Included | Included |
| **`09`** | Recreation and culture | **1.902%** | Included | Included |
| **`10`** | Education | **1.472%** | Included | Included |
| **`11`** | Restaurants and hotels | **5.861%** | Included | Included |
| **`12`** | Miscellaneous goods and services | **2.182%** | Included | Included |
| **TOTAL** | **Full National Basket** | **100.000%** | **100.000%** | **52.200%** |

### 5.3 Aggregation Formulas
In [`pipeline/cpi_calculator.py`](file:///D:/CPI%20PIPELINE/pipeline/cpi_calculator.py):

#### Headline Daily CPI:
$$CPI_{\text{headline}}^t = \frac{\sum_{d=1}^{12} W_d \cdot I_d^{t/0}}{\sum_{d \in \text{active}} W_d} \times S_{y}$$

#### Core Daily CPI (Excluding Food & Energy shocks):
$$CPI_{\text{core}}^t = \frac{\sum_{d \notin \{01, 04, 07\}} W_d \cdot I_d^{t/0}}{\sum_{d \notin \{01, 04, 07\}} W_d} \times S_{y}$$

> **Chain-Linking Splice Factor ($S_y$):**
> To ensure seamless annual rebasing without January 1 step jumps, the calculation engine dynamically queries `gold.cpi_base_dates` for the active December average:
> $$S_y = \frac{\bar{I}_{\text{Dec}, y-1}}{100.0}$$
> For the initial base year (2026), $S = 1.0000$. Subsequent rebased series scale continuously by $S_y$ back to project inception (August 18, 2026 = 100.00).

---

## 6. End-to-End Walkthrough: Calculating Rice Weight

To see how all pieces connect, follow a single product category from raw scrape to national CPI:

```
[Raw Scrape]  "APSOR JASMINE RICE 5KG" = 26,300 KHR
      │
      ▼
[Unit Norm]   26,300 KHR / 5 kg = 5,260 KHR/kg
      │
      ▼
[Jevons]      Combine 4 rice brands equally (1/4 weight each) -> Class 01.1.1 Index = 102.58
      │
      ▼
[Intra-Div]   Rice has weight 41.295% inside Food -> Division 01 Index = 101.065
      │
      ▼
[National]    Food has weight 44.800% in National CPI
              National Rice Weight = 44.800% × 41.295% = 18.500%
              National Headline CPI = 100.477 (+0.48% inflation)
```

---

## 7. Key Takeaways & Reference Summary

1. **Item / Brand Level:** Uses **Equal Weight** ($1/N$) via the Jevons geometric mean because e-commerce scrapers lack point-of-sale volume data.
2. **Intra-Division Weight ($w_{c \mid d}$):** The proportion of money spent on a subclass *within that specific division* ($\sum = 100\%$).
3. **National Weight ($W_d$ / $W_c$):** The proportion of money spent on an item or division *across the entire country's economy* ($\sum = 100\%$).
4. **Source of Truth:** The official **Cambodia Socio-Economic Survey (CSES)** published by the **National Institute of Statistics (NIS)**, Ministry of Planning.
