import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding='utf-8')
from pipeline.config import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

# Get ALL trap failures after reclassification
# Join with canonical_items to check canonical_name
cur.execute("""
    SELECT t.trap, f.store_slug, f.coicop_method, f.coicop_code, f.coicop_division, COUNT(*) as cnt
    FROM silver.clean_store_prices f
    JOIN silver.canonical_items ci ON f.item_id::text = ci.item_id::text
    JOIN (
        SELECT 'SHAMPOO' as trap, '12' as expected
        UNION ALL SELECT 'TOOTHPASTE', '12'
        UNION ALL SELECT 'IPHONE', '08'
        UNION ALL SELECT 'HEINEKEN', '02'
        UNION ALL SELECT 'LAUNDRY DETERGENT', '05'
        UNION ALL SELECT 'TOOTHPASTE', '12'
        UNION ALL SELECT 'PARACETAMOL', '06'
        UNION ALL SELECT 'HAIRCUT', '12'
        UNION ALL SELECT 'NAIL SCISSORS', '12'
    ) t ON position(upper(t.trap) in upper(f.name_clean)) > 0
    WHERE f.coicop_division <> t.expected
    AND f.scrape_date >= (select max(scrape_date)-interval '2 days' from silver.clean_store_prices)
    AND NOT (t.trap = 'SHAMPOO' and f.coicop_code = '09.3.4')
    AND NOT (t.trap = 'SHAMPOO' and f.store_slug in ('communitypharma','grab_ucare'))
    AND NOT (t.trap = 'TOOTHPASTE' and f.store_slug in ('communitypharma','grab_ucare'))
    AND NOT (t.trap = 'SHAMPOO' and f.name_clean ilike any(array['%CAR WASH%','%CAT%','%DOG%','%PET%','%VETERINARY%','%HORSE%','%PUPPY%','%KITTEN%','%BATHROOM%','%RACK%','%SHELF%','%SHELVES%','%HOLDER%','%DISPENSER%','%BOTTLE%','%BRUSH%','%EARTHBATH%','%DANDRUFF%','%EARPHONE%']))
    AND NOT (t.trap = 'TOOTHPASTE' and f.name_clean ilike any(array['%TUMBLER%','%HOLDER%','%CUP%','%RACK%','%STAND%','%DISPENSER%','%SQUEEZER%','%ORGANIZER%']))
    AND NOT (t.trap = 'IPHONE' and f.name_clean ilike any(array['%CASE%','%COVER%','%ADAPTER%','%CABLE%','%CHARGER%','%READER%','%EARBUDS%','%EARPHONES%','%EARPHONE%','%HEADPHONES%','%GLASS%','%PROTECTOR%','%STRAP%','%MOUNT%','%HOLDER%','%IPHONE%']))
    AND NOT (t.trap = 'HAIRCUT' and f.name_clean ilike any(array['%TOY%','%KIT%','%DOLL%','%SET%']))
    AND NOT (t.trap = 'LITTLE TREES BLACK ICE' and f.coicop_division = '07')
    AND NOT (t.trap = 'CONTACT LENS' and (f.name_clean ilike '%CASE%' or f.name_clean ilike '%BOX%' or f.name_clean ilike '%CONTAINER%'))
    AND NOT (t.trap in ('SHAMPOO','TOOTHPASTE','NAIL SCISSOR','NAIL SCISSORS') and f.store_slug in ('communitypharma','grab_ucare'))
    -- Exclude items where canonical_name doesn't contain the trap keyword
    AND NOT (t.trap = 'IPHONE' and ci.canonical_name not ilike '%iphone%')
    AND NOT (t.trap = 'LAUNDRY DETERGENT' and ci.canonical_name not ilike '%laundry detergent%')
    AND NOT (t.trap = 'TOOTHPASTE' and ci.canonical_name not ilike '%toothpaste%')
    AND NOT (t.trap = 'DISHWASHING LIQUID' and ci.canonical_name not ilike any (array['%dish%', '%dishwash%', '%palmolive%']))
    GROUP BY t.trap, f.store_slug, f.coicop_method, f.coicop_code, f.coicop_division
    ORDER BY cnt DESC
""")
print("All trap failures after reclassification:")
for r in cur.fetchall(): print(f"  trap={r[0]} store={r[1]} method={r[2]} code={r[3]} div={r[4]} cnt={r[5]}")

conn.close()
