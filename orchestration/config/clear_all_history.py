"""
clear_all_history.py
───────────────────
Script to pause all DAGs and completely clear all historical DAG runs,
task instances, XComs, logs, and execution history from Airflow metadata database.
"""

from airflow.models import (
    DagModel,
    DagRun,
    Log,
    RenderedTaskInstanceFields,
    TaskInstance,
    TaskReschedule,
    XCom,
)
from airflow.utils.session import create_session


def clear_airflow_history():
    print("Connecting to Airflow metadata database...")
    with create_session() as session:
        # Pause all DAGs
        dags = session.query(DagModel).all()
        for dag in dags:
            dag.is_paused = True
            print(f"Paused DAG: {dag.dag_id}")

        # Clear all task execution tables
        ti_count = session.query(TaskInstance).delete(synchronize_session=False)
        dr_count = session.query(DagRun).delete(synchronize_session=False)
        xc_count = session.query(XCom).delete(synchronize_session=False)
        log_count = session.query(Log).delete(synchronize_session=False)

        try:
            session.query(TaskReschedule).delete(synchronize_session=False)
        except Exception:
            pass

        try:
            session.query(RenderedTaskInstanceFields).delete(synchronize_session=False)
        except Exception:
            pass

        session.commit()
        print("Database cleared successfully:")
        print(f"  - TaskInstances removed: {ti_count}")
        print(f"  - DagRuns removed: {dr_count}")
        print(f"  - XComs removed: {xc_count}")
        print(f"  - Logs removed: {log_count}")


if __name__ == "__main__":
    clear_airflow_history()
