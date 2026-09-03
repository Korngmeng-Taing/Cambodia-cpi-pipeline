"""
=============================================================================
CAMBODIA DAILY CPI — GOLD LAYER CALCULATION DAG (03:30 AM ICT)
Triggers after Silver DAG completes:
  1. Computes Jevons micro-indices with 7-day missing price imputation.
  2. Aggregates 12 COICOP division indices with official NIS expenditure weights.
  3. Computes Headline CPI, Core CPI (ex-food & energy), and daily inflation.

REBASING POLICY (see docs/rebasing_policy.md):
  - Base period is the average of the preceding December (ILO CPI Manual §9.41).
  - Annual rebasing occurs on Jan 1 (or first business day) via the `annual_rebase_cpi`
    task. The new base_date is written to the Airflow Variable `cpi_base_date`.
  - The daily calculation always reads `cpi_base_date` (fallback: 2026-08-18).
=============================================================================
"""

import sys
import os
sys.path.insert(0, "/opt/airflow")

from datetime import datetime, timedelta, date
import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable

from pipeline.cpi_calculator import CPICalculationEngine
from ml.nowcaster import execute_nowcasting_pipeline

DEFAULT_ARGS = {
    "owner": "cpi-data-team",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

def get_base_date(target_date: date | None = None) -> date:
    """Fetch the applicable base date for a given target_date from the
    date-effective lookup table ``gold.cpi_base_dates``.

    Falls back to the Airflow Variable ``cpi_base_date`` → env var
    ``CPI_DEFAULT_BASE_DATE`` → project inception date if the table
    doesn't exist or has no rows yet.
    """
    if target_date is None:
        target_date = date.today()

    try:
        import psycopg2
        from pipeline.config import get_database_url
        conn_str = get_database_url().replace("postgresql+psycopg2://", "postgresql://", 1)
        with psycopg2.connect(conn_str) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT base_date FROM gold.cpi_base_dates
                    WHERE effective_from <= %s
                    ORDER BY effective_from DESC
                    LIMIT 1
                """, (target_date,))
                row = cur.fetchone()
                if row:
                    return row[0]
    except Exception:
        pass  # Table may not exist yet; fall through to legacy lookup

    try:
        base_str = Variable.get("cpi_base_date")
        return datetime.strptime(base_str, "%Y-%m-%d").date()
    except (KeyError, ValueError):
        pass

    # Last resort: configurable via env var (avoids hardcoding in source).
    env_default = os.getenv("CPI_DEFAULT_BASE_DATE", "2026-08-18")
    try:
        return datetime.strptime(env_default, "%Y-%m-%d").date()
    except ValueError:
        return date(2026, 8, 18)

def execute_daily_cpi_calculation(**context):
    logical_date_str = context.get("ds")
    if logical_date_str:
        calc_date = datetime.strptime(logical_date_str, "%Y-%m-%d").date()
    else:
        calc_date = date.today()

    base_date = get_base_date(calc_date)
    print(f"🚀 Starting Gold CPI Calculation for {calc_date} (Base Date: {base_date})...")

    engine = CPICalculationEngine()
    engine.run_daily_pipeline(target_date=calc_date, base_date=base_date)
    print(f"✅ Gold CPI Calculation completed successfully for {calc_date}!")

def execute_monthly_cpi_calculation(**context):
    logical_date_str = context.get("ds")
    if logical_date_str:
        calc_date = datetime.strptime(logical_date_str, "%Y-%m-%d").date()
    else:
        calc_date = date.today()

    print(f"🚀 Updating Monthly CPI Mart for {calc_date}...")
    engine = CPICalculationEngine()
    df_monthly = engine.compute_monthly_cpi()
    engine.save_monthly_cpi(df_monthly)
    print(f"✅ Monthly CPI calculation and persistence complete!")

def annual_rebase_cpi(**context):

    """
    Annual rebasing task: runs on Jan 1 (or first business day).
    Picks the date in December with the most price observations as the new
    base date (more representative than always anchoring to Dec 1, which
    may be missing data in many years).

    IMPORTANT: Base dates are stored in a date-effective lookup table
    ``gold.cpi_base_dates`` so that historical backfills always use the
    correct base date for their execution period. The Airflow Variable
    is also updated for backward compatibility.
    """
    logical_date_str = context.get("ds")
    if logical_date_str:
        run_date = datetime.strptime(logical_date_str, "%Y-%m-%d").date()
    else:
        run_date = date.today()

    # Only run in January
    if run_date.month != 1:
        print(f"⏭️ Skipping annual rebase: not January (current month: {run_date.month})")
        return

    # Determine preceding December
    dec_year = run_date.year - 1
    dec_start = date(dec_year, 12, 1)
    dec_end = date(dec_year, 12, 31)

    engine = CPICalculationEngine()
    df_dec = engine.load_clean_prices(dec_start, dec_end)

    if df_dec.empty:
        print(f"⚠️ No price data for December {dec_year}; rebasing skipped.")
        return

    # Pick the date in December with the most price observations — more
    # representative than always anchoring to Dec 1, which may be missing data.
    obs_by_date = df_dec.groupby("scrape_date")["item_id"].count()
    new_base = obs_by_date.idxmax()
    effective_from = date(run_date.year, 1, 1)

    # Determine prior active base date to evaluate December price level relative to current series
    import psycopg2
    from pipeline.config import get_database_url
    conn_str = get_database_url().replace("postgresql+psycopg2://", "postgresql://", 1)
    prior_base = None
    try:
        with psycopg2.connect(conn_str) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT base_date FROM gold.cpi_base_dates WHERE effective_from <= %s ORDER BY effective_from DESC LIMIT 1;",
                    (dec_start,),
                )
                row = cur.fetchone()
                if row and row[0]:
                    prior_base = row[0]
    except Exception:
        pass

    if not prior_base:
        prior_base_str = Variable.get("cpi_base_date", default_var=None)
        if prior_base_str:
            try:
                prior_base = date.fromisoformat(prior_base_str)
            except Exception:
                pass

    # Compute average December headline CPI across all days with data
    dec_dates = sorted(df_dec["scrape_date"].unique())
    cpi_values = []

    if prior_base:
        df_prior_base = engine.load_clean_prices(prior_base, prior_base)
        base_df = engine.compute_base_prices(prior_base, df_prior_base) if not df_prior_base.empty else engine.compute_base_prices(new_base, df_dec)
    else:
        base_df = engine.compute_base_prices(new_base, df_dec)

    for d in dec_dates:
        try:
            elem = engine.compute_daily_elementary_indices(d, base_df, df_dec)
            _, headline = engine.aggregate_division_and_headline(elem, d)
            cpi_values.append(headline["headline_cpi"])
        except Exception:
            continue

    if cpi_values:
        avg_cpi = sum(cpi_values) / len(cpi_values)

        # Persist to date-effective lookup table (backfill-safe)
        import psycopg2
        from pipeline.config import get_database_url
        conn_str = get_database_url().replace("postgresql+psycopg2://", "postgresql://", 1)
        with psycopg2.connect(conn_str) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS gold.cpi_base_dates (
                        effective_from DATE PRIMARY KEY,
                        base_date DATE NOT NULL,
                        avg_december_cpi NUMERIC(10, 4),
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                cur.execute("""
                    INSERT INTO gold.cpi_base_dates (effective_from, base_date, avg_december_cpi)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (effective_from) DO UPDATE
                    SET base_date = EXCLUDED.base_date,
                        avg_december_cpi = EXCLUDED.avg_december_cpi;
                """, (effective_from, new_base, avg_cpi))
            conn.commit()

        # Also update Airflow Variable for backward compatibility
        Variable.set("cpi_base_date", new_base.strftime("%Y-%m-%d"))
        print(f"✅ Annual rebasing complete: new base_date = {new_base} (most-observed Dec date) effective from {effective_from} (avg December CPI: {avg_cpi:.2f})")
    else:
        print(f"⚠️ Could not compute December average CPI; rebasing skipped.")

local_tz = pendulum.timezone("Asia/Phnom_Penh")

with DAG(
    dag_id="gold_cpi_dag",
    default_args=DEFAULT_ARGS,
    description="Daily Jevons & Laspeyres CPI Economic Calculation Engine (triggered by cpi_master_dag)",
    schedule=None,  # Triggered by cpi_master_dag, not cron — avoids double execution
    start_date=pendulum.datetime(2026, 8, 18, tz=local_tz),
    catchup=False,
    tags=["gold", "cpi", "inflation", "economics", "jevons", "laspeyres"],
) as dag:

    calculate_cpi_task = PythonOperator(
        task_id="calculate_daily_cpi_indices",
        python_callable=execute_daily_cpi_calculation,
    )

    calculate_monthly_cpi_task = PythonOperator(
        task_id="calculate_monthly_cpi_indices",
        python_callable=execute_monthly_cpi_calculation,
    )

    nowcast_cpi_task = PythonOperator(
        task_id="nowcast_monthly_inflation",
        python_callable=execute_nowcasting_pipeline,
    )

    annual_rebase_task = PythonOperator(
        task_id="annual_rebase_cpi",
        python_callable=annual_rebase_cpi,
    )

    calculate_cpi_task >> calculate_monthly_cpi_task >> nowcast_cpi_task >> annual_rebase_task

