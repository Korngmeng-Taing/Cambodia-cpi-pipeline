import os
import sys
import re
import psycopg2
from psycopg2.extras import RealDictCursor

def main():
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    mb_host = os.getenv("METABASE_DB_HOST", os.getenv("POSTGRES_HOST", "localhost"))
    cpi_host = os.getenv("CPI_DB_HOST", os.getenv("POSTGRES_HOST", "localhost"))
    mb_port = int(os.getenv("POSTGRES_PORT", 5432))
    cpi_port = int(os.getenv("POSTGRES_PORT", 5432))

    conn_mb = psycopg2.connect(f"postgresql://metabase:metabase@{mb_host}:{mb_port}/metabase")
    conn_cpi = psycopg2.connect(f"postgresql://cpi_user:cpi_pass@{cpi_host}:{cpi_port}/cpi_db")
    # BUG FIX: Prevent Metabase cards from mutating the CPI database.
    # Without this, a malicious/accidental DELETE/DROP in a card query
    # would permanently alter production data.
    conn_cpi.set_session(readonly=True)

    print("=" * 80)
    print(" METABASE CARDS AUDIT & SQL DIAGNOSTIC TEST")
    print("=" * 80)

    with conn_mb.cursor(cursor_factory=RealDictCursor) as cur_mb:
        cur_mb.execute("""
            SELECT d.id as dash_id, d.name as dash_name, c.id as card_id, c.name as card_name, c.display, c.dataset_query
            FROM report_dashboardcard dc
            JOIN report_dashboard d ON dc.dashboard_id = d.id
            JOIN report_card c ON dc.card_id = c.id
            WHERE d.archived = false
            ORDER BY d.id, c.id;
        """)
        cards = cur_mb.fetchall()

    print(f"Found {len(cards)} active cards across all dashboards.\n")

    with conn_cpi.cursor(cursor_factory=RealDictCursor) as cur_cpi:
        for c in cards:
            dash_id = c["dash_id"]
            _dash_name = c["dash_name"]
            card_id = c["card_id"]
            card_name = c["card_name"]
            display = c["display"]
            q_obj = c["dataset_query"]

            sql = ""
            if isinstance(q_obj, dict) and "native" in q_obj and "query" in q_obj["native"]:
                sql = q_obj["native"]["query"]
            elif isinstance(q_obj, str):
                import json
                try:
                    parsed = json.loads(q_obj)
                    sql = parsed.get("native", {}).get("query", "")
                except Exception:
                    sql = q_obj

            if not sql:
                print(f"[FAIL] Dash {dash_id} | Card {card_id} '{card_name}' ({display}) -> NO SQL QUERY FOUND")
                continue

            try:
                # Strip Metabase optional template clauses [[ ... ]] so test evaluates base query
                clean_sql = re.sub(r'\[\[.*?\]\]', '', sql, flags=re.DOTALL)
                cur_cpi.execute(clean_sql)
                rows = cur_cpi.fetchall()
                conn_cpi.rollback()  # BUG FIX: Always rollback to clear transaction state
                row_cnt = len(rows)
                sample = rows[0] if row_cnt > 0 else "EMPTY RESULT"
                print(f"[OK] Dash {dash_id} | Card {card_id} '{card_name}' ({display}) -> {row_cnt} rows. Sample: {sample}")
            except Exception as e:
                conn_cpi.rollback()
                print(f"[ERROR] Dash {dash_id} | Card {card_id} '{card_name}' ({display}) -> EXCEPTION: {e}")
                print(f"   Failed SQL:\n{sql}\n")

    conn_mb.close()
    conn_cpi.close()
    print("=" * 80)


if __name__ == "__main__":
    main()
