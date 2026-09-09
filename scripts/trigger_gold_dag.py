"""
scripts/trigger_gold_dag.py
───────────────────────────
Triggers gold_cpi_dag via Airflow REST API and monitors task completion.
"""
import sys
import time
import requests
from requests.auth import HTTPBasicAuth

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

AIRFLOW_URL = "http://localhost:8085/api/v1"
AUTH = HTTPBasicAuth("admin", "admin")

def main():
    print("=" * 60)
    print("TRIGGERING GOLD_CPI_DAG (ds: 2026-09-09)")
    print("=" * 60)

    # 1. Trigger dag run
    payload = {
        "conf": {"ds": "2026-09-09"}
    }
    r = requests.post(f"{AIRFLOW_URL}/dags/gold_cpi_dag/dagRuns", json=payload, auth=AUTH)
    if r.status_code not in (200, 201):
        print(f"Failed to trigger DAG: HTTP {r.status_code} - {r.text}")
        sys.exit(1)

    dag_run = r.json()
    dag_run_id = dag_run["dag_run_id"]
    print(f"✅ Triggered run: {dag_run_id}")

    # 2. Poll status
    max_wait = 120  # 2 minutes max
    start_time = time.time()
    while time.time() - start_time < max_wait:
        time.sleep(3)
        status_r = requests.get(f"{AIRFLOW_URL}/dags/gold_cpi_dag/dagRuns/{dag_run_id}", auth=AUTH)
        if status_r.status_code == 200:
            state = status_r.json().get("state")
            elapsed = int(time.time() - start_time)
            print(f"[{elapsed:02d}s] DAG Run State: {state}")
            if state in ("success", "failed"):
                break
        else:
            print(f"Failed to poll status: HTTP {status_r.status_code}")

    # 3. Fetch Task Instances
    ti_r = requests.get(f"{AIRFLOW_URL}/dags/gold_cpi_dag/dagRuns/{dag_run_id}/taskInstances", auth=AUTH)
    if ti_r.status_code == 200:
        tis = ti_r.json().get("task_instances", [])
        print("\nTask Instances Status:")
        all_success = True
        for ti in tis:
            t_id = ti.get("task_id")
            t_state = ti.get("state")
            t_dur = ti.get("duration")
            dur_str = f"{t_dur:.2f}s" if t_dur is not None else "N/A"
            print(f"  • {t_id:30s}: {t_state:10s} ({dur_str})")
            if t_state != "success":
                all_success = False

        if all_success:
            print("\n🎉 ALL TASKS IN gold_cpi_dag EXECUTED SUCCESSFULLY!")
        else:
            print("\n❌ Some tasks failed or did not complete.")
            sys.exit(1)
    else:
        print(f"Failed to fetch task instances: HTTP {ti_r.status_code}")

if __name__ == "__main__":
    main()
