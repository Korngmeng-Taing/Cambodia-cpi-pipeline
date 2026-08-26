import argparse
import os
import sys

sys.path.insert(0, os.path.abspath("."))
from pipeline.config import get_db_connection


def clear_db_locks(dry_run: bool = False, force: bool = False):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT pid, usename, client_addr, state, state_change, query
                FROM pg_stat_activity
                WHERE pid <> pg_backend_pid()
                  AND datname = 'cpi_db'
                  AND (
                    (state = 'idle in transaction' AND state_change < NOW() - INTERVAL '5 minutes')
                    OR pid IN (SELECT unnest(pg_blocking_pids(p.pid)) FROM pg_stat_activity p)
                  );
            """)
            stuck_sessions = cur.fetchall()

            if not stuck_sessions:
                print("No stuck or blocking database locks found.")
                return

            print(f"Found {len(stuck_sessions)} stuck / blocking process(es):")
            for pid, user, addr, state, changed, query in stuck_sessions:
                snippet = (query or "").strip().replace("\n", " ")[:60]
                print(f"  PID {pid} | User: {user} | State: {state} | Changed: {changed} | Query: {snippet}...")

            if dry_run:
                print("\n[DRY RUN] No processes were terminated.")
                return

            if not force:
                confirm = input("\nTerminate these sessions? [y/N]: ").strip().lower()
                if confirm not in ("y", "yes"):
                    print("Aborted by user. No processes terminated.")
                    return

            pids = [s[0] for s in stuck_sessions]
            cur.execute(
                "SELECT pid, pg_terminate_backend(pid) FROM unnest(%s::int[]) AS pid;",
                (pids,),
            )
            terminated = cur.fetchall()
            print(f"Successfully terminated {len(terminated)} blocking process(es).")
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Safely terminate stuck or blocking PostgreSQL sessions in cpi_db.")
    parser.add_argument("--dry-run", action="store_true", help="List stuck sessions without terminating them.")
    parser.add_argument("--force", action="store_true", help="Terminate without interactive prompt.")
    args = parser.parse_args()

    clear_db_locks(dry_run=args.dry_run, force=args.force)
