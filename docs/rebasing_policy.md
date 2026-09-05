# Cambodia Daily CPI — Annual Rebasing Policy

**Effective Date:** 2026-08-18  
**Reference Standard:** ILO CPI Manual (2020), Chapter 9 — Index Number Formulae and Rebasings

---

## 1. Base Period Definition

The base period for the Cambodia Daily CPI is the **average of the preceding December**, in accordance with ILO CPI Manual §9.41.

- Let $D_{y}$ be the set of calendar days in December of year $y$.
- The base index for year $y+1$ is computed as:

$$I_{\text{base}, y+1} = \frac{1}{|D_{y}|} \sum_{d \in D_{y}} I_{\text{headline}}(d)$$

where $I_{\text{headline}}(d)$ is the headline CPI published for day $d$.

- The **base date** is dynamically selected as the date in December of year $y$ with the **highest number of observed prices** (ensuring maximum basket coverage, rather than arbitrarily anchoring to Dec 1).
- The base date and December average CPI are persisted in the date-effective lookup table `gold.cpi_base_dates` and mirrored to the Airflow Variable `cpi_base_date` for backward compatibility.

---

## 2. Rebasing Schedule

| Event | Timing | Action |
|-------|--------|--------|
| **Annual Rebase** | January 1 (or first business day) of each year | The `annual_rebase_cpi` task in `gold_cpi_dag` runs, computes the December average, writes to `gold.cpi_base_dates`, and updates the Airflow Variable `cpi_base_date`. |
| **Daily Calculation** | Daily during Gold CPI DAG execution | `CPICalculationEngine` queries `gold.cpi_base_dates` (fallback: `cpi_base_date` Variable → `2026-08-18`) and computes indices relative to that base. |

---

## 3. Operational Procedure

1. **On January 1 (or first business day):**
   - The `annual_rebase_cpi` task executes.
   - It loads all clean prices for the preceding December (Dec 1–31).
   - It identifies the date with the highest observation count (`obs_by_date.idxmax()`).
   - It runs the CPI engine across December dates to compute the average December headline CPI.
   - It upserts into `gold.cpi_base_dates (effective_from, base_date, avg_december_cpi)`.
   - It updates the Airflow Variable `cpi_base_date` with the new base date.

2. **Subsequent daily runs:**
   - `calculate_daily_cpi_indices` reads `Variable.get("cpi_base_date")`.
   - If the variable is missing or malformed, it falls back to `2026-08-18` (project inception).
   - All indices are expressed relative to the December-average base level.

---

## 4. Series Continuity & Chain-Linking Splice Factor

- **No series break:** Rebasings are *chain-linking* operations. Under ILO CPI Manual §9.35–§9.42, when the base period shifts from year $y$ to year $y+1$, the new series is linked to the continuous historical series using the **chain-linking splice factor** ($S$):

$$S_{y+1} = \frac{\bar{I}_{\text{Dec}, y}^{\text{continuous}}}{100.0}$$

where $\bar{I}_{\text{Dec}, y}^{\text{continuous}}$ is the average December headline CPI evaluated on the continuous series scale (persisted in `gold.cpi_base_dates.avg_december_cpi`).

- **Index Splicing Formula:** For any day $t$ in year $y+1$ calculated relative to the new December base date:

$$I_t^{\text{continuous}} = I_t^{\text{new\_base}} \times S_{y+1}$$

This scaling is applied consistently across all 12 COICOP division indices, Headline CPI, and Core CPI in `pipeline/cpi_calculator.py:aggregate_division_and_headline(splice_factor=...)`.

- **Multi-Year Continuity:** When `annual_rebase_cpi` evaluates the preceding December, it applies the prior year's splice factor ($S_y$), ensuring the new December average and splice factor ($S_{y+1}$) remain strictly chained back to project inception (August 18, 2026 = 100.00) without series drift or discontinuities.
- **Historical revision:** When a rebase occurs, published historical records are *not* revised. The continuous series maintains backward comparability while reflecting updated representative baskets.

---

## 5. Airflow Variable

| Variable Key | Format | Example | Description |
|--------------|--------|---------|-------------|
| `cpi_base_date` | `YYYY-MM-DD` | `2026-12-01` | First day of the December used as the base period. Updated annually by `annual_rebase_cpi`. |

---

## 6. Edge Cases

- **Missing December data:** If the preceding December has < 15 valid calculation days, rebasing is skipped and the previous base is retained. An alert is sent.
- **Mid-year inception:** The initial base (2026-08-18) is a *fixed* inception base. The first annual rebase will occur on 2027-01-01 using December 2026 data.
- **Manual override:** Operators may manually set `cpi_base_date` via the Airflow UI (Admin → Variables) if an off-cycle rebase is required. The next automatic rebase will overwrite it.

---

## 7. Audit Trail

Every rebase execution writes a log entry:

```
✅ Annual rebasing complete: new base_date = YYYY-12-01
```

The previous and new base dates are also captured in the task instance XCom for traceability.