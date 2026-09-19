"""Check non-official codes in new items."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from dotenv import load_dotenv
load_dotenv()
import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, dbname='cpi_db', user='postgres', password='postgres')
cur = conn.cursor()

# Get all non-official codes in clean_store_prices for new items
cur.execute("""SELECT csp.coicop_code, COUNT(*) FROM silver.clean_store_prices csp 
WHERE csp.item_id NOT IN (SELECT CAST(item_id AS text) FROM silver.canonical_items)
AND csp.coicop_code NOT IN (SELECT coicop_code FROM gold.cambodia_cpi_coicop_weights_breakdown)
GROUP BY csp.coicop_code ORDER BY csp.coicop_code""")
print("=== Non-official codes in new items ===")
for r in cur.fetchall(): print(f"  {r[0]}: {r[1]:,}")

# Count distinct items with non-official codes
cur.execute("""SELECT COUNT(DISTINCT item_id) FROM silver.clean_store_prices 
WHERE item_id NOT IN (SELECT CAST(item_id AS text) FROM silver.canonical_items)
AND coicop_code NOT IN (SELECT coicop_code FROM gold.cambodia_cpi_coicop_weights_breakdown)""")
print(f"\nDistinct new items with non-official codes: {cur.fetchone()[0]:,}")

# Total new items
cur.execute("""SELECT COUNT(DISTINCT item_id) FROM silver.clean_store_prices 
WHERE item_id NOT IN (SELECT CAST(item_id AS text) FROM silver.canonical_items)""")
print(f"Total distinct new items: {cur.fetchone()[0]:,}")

conn.close()
