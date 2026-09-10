import psycopg2
conn = psycopg2.connect('postgresql://airflow:airflow@postgres:5432/cpi_db')
cur = conn.cursor()
cur.execute("SELECT pattern FROM silver.coicop_critical_traps")
for r in cur.fetchall():
    p = r[0]
    if '(' in p or ')' in p:
        print(repr(p))
cur.close()
conn.close()
