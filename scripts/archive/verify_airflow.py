"""
scripts/verify_airflow.py
─────────────────────────
Queries the Airflow REST API to check:
1. DAG import errors
2. Master DAG (cpi_master_dag) & Gold CPI DAG (gold_cpi_dag) status
3. Unpauses gold_cpi_dag and triggers a validation run if requested.
"""
import sys
import requests
from requests.auth import HTTPBasicAuth

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

AIRFLOW_URL = "http://localhost:8085/api/v1"
AUTH = HTTPBasicAuth("admin", "admin")

def main():
    print("=" * 60)
    print("AIRFLOW ORCHESTRATION VERIFICATION")
    print("=" * 60)

    # 1. Check Import Errors
    r_err = requests.get(f"{AIRFLOW_URL}/importErrors", auth=AUTH, timeout=10)
    if r_err.status_code == 200:
        errs = r_err.json().get("import_errors", [])
        if errs:
            print(f"⚠️ Found {len(errs)} DAG import errors:")
            for e in errs:
                print(f"  - {e.get('filename')}: {e.get('stack_trace')[:200]}...")
        else:
            print("✅ Zero DAG import errors detected in Airflow!")
    else:
        print(f"Failed to fetch import errors: HTTP {r_err.status_code}")

    # 2. Check Target DAGs
    target_dags = ["cpi_master_dag", "gold_cpi_dag", "silver_dag", "gold_dag"]
    print("\nChecking Pipeline DAGs Status:")
    for dag_id in target_dags:
        r_dag = requests.get(f"{AIRFLOW_URL}/dags/{dag_id}", auth=AUTH, timeout=10)
        if r_dag.status_code == 200:
            info = r_dag.json()
            is_paused = info.get("is_paused")
            print(f"  • {dag_id:20s}: Active (Paused: {is_paused})")
        else:
            print(f"  • {dag_id:20s}: Not found / HTTP {r_dag.status_code}")

    # 3. Check Recent Runs for gold_cpi_dag
    print("\nRecent Runs for gold_cpi_dag:")
    r_runs = requests.get(f"{AIRFLOW_URL}/dags/gold_cpi_dag/dagRuns?limit=5&order_by=-execution_date", auth=AUTH, timeout=10)
    if r_runs.status_code == 200:
        runs = r_runs.json().get("dag_runs", [])
        for run in runs:
            print(f"  • Run ID: {run.get('dag_run_id')} | State: {run.get('state')} | Execution: {run.get('logical_date') or run.get('execution_date')}")
    else:
        print(f"Failed to fetch dag runs: HTTP {r_runs.status_code}")

if __name__ == "__main__":
    main()
