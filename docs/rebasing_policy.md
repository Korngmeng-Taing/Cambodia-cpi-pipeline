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

- The **base date** (`cpi_base_date` Airflow Variable) is set to **December 1 of year $y$** (i.e., the first day of the averaging window). This is a symbolic anchor; the actual base level is the December average.

---

## 2. Rebasing Schedule

| Event | Timing | Action |
|-------|--------|--------|
| **Annual Rebase** | January 1 (or first business day) of each year | The `annual_rebase_cpi` task in `gold_cpi_dag` runs, computes the December average, and writes the new `cpi_base_date` to the Airflow Variable `cpi_base_date`. |
| **Daily Calculation** | Every day at 03:30 AM ICT | The `calculate_daily_cpi_indices` task reads `cpi_base_date` (fallback: 2026-08-18) and computes indices relative to that base. |

---

## 3. Operational Procedure

1. **On January 1 (or first business day):**
   - The `annual_rebase_cpi` task executes.
   - It loads all clean prices for the preceding December (Dec 1–31).
   - It runs the full CPI pipeline for each day in that window to obtain daily headline CPI values.
   - It computes the arithmetic mean of those daily headline CPI values.
   - It sets `cpi_base_date = "YYYY-12-01"` (the first day of that December) in the Airflow Variable `cpi_base_date`.

2. **Subsequent daily runs:**
   - `calculate_daily_cpi_indices` reads `Variable.get("cpi_base_date")`.
   - If the variable is missing or malformed, it falls back to `2026-08-18` (project inception).
   - All indices are expressed relative to the December-average base level.

---

## 4. Series Continuity

- **No series break:** Rebasings are *linking* operations. The published index level on the rebase day equals the December average, so the time series is continuous.
- **Historical revision:** When a rebase occurs, the entire published history is *not* revised. Only the base reference changes. Downstream consumers should use the `base_date` column in `gold.fct_daily_cpi` to interpret the index level.

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