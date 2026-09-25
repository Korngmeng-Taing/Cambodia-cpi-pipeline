"""
scripts/reclassify_canonical_to_5digit.py
─────────────────────────────────────────
Upgrades all canonical items in silver.canonical_items to UN COICOP 2018 5-digit codes
(format: DD.G.C.S) while preserving 100% hierarchical roll-up compatibility with the
Cambodia NIS 4-digit Laspeyres aggregation engine.

Covers all 12 COICOP divisions with deterministic, high-accuracy bilingual (Khmer/English)
domain rules.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import psycopg2
from pipeline.config import get_database_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("reclassify_5digit")

SQL_RECLASSIFICATION = r"""
-- 1. Division 01: Food & Non-Alcoholic Beverages
-- 01.1.1 Bread & cereals
UPDATE silver.canonical_items
SET coicop_code = CASE
    WHEN canonical_name ~* '(rice|អង្ករ|jasmine|phka|glutinous|basmati|berry rice)' THEN '01.1.1.1'
    WHEN canonical_name ~* '(bread|baguette|croissant|sandwich|toast|brioche|នំប៉័ង)' THEN '01.1.1.2'
    WHEN canonical_name ~* '(noodle|pasta|spaghetti|macaroni|ramen|vermicelli|udon|soba|មី|គុយទាវ)' THEN '01.1.1.3'
    WHEN canonical_name ~* '(biscuit|cracker|cookie|wafer|oreo|ritz|នំស្រួយ)' THEN '01.1.1.4'
    WHEN canonical_name ~* '(cake|pastry|muffin|pie|tart|donut|doughnut|waffle|pancake|នំ)' THEN '01.1.1.5'
    WHEN canonical_name ~* '(flour|oat|cereal|cornflake|muesli|granola|ម្សៅ)' THEN '01.1.1.9'
    ELSE '01.1.1.9'
END
WHERE coicop_code = '01.1.1';

-- 01.1.2 Meat
UPDATE silver.canonical_items
SET coicop_code = CASE
    WHEN canonical_name ~* '(pork|pig|bacon|ham|lard|ribs|belly|សាច់ជ្រូក)' THEN '01.1.2.1'
    WHEN canonical_name ~* '(beef|steak|veal|bovine|angus|wagyu|សាច់គោ)' THEN '01.1.2.2'
    WHEN canonical_name ~* '(chicken|poultry|wing|breast|drumstick|សាច់មាន់)' THEN '01.1.2.3'
    WHEN canonical_name ~* '(duck|goose|សាច់ទា)' THEN '01.1.2.4'
    WHEN canonical_name ~* '(sausage|hotdog|salami|meatball|paté|pate|សាច់ក្រក)' THEN '01.1.2.5'
    ELSE '01.1.2.9'
END
WHERE coicop_code = '01.1.2';

-- 01.1.3 Fish & seafood
UPDATE silver.canonical_items
SET coicop_code = CASE
    WHEN canonical_name ~* '(shrimp|prawn|crab|squid|octopus|lobster|mussel|clam|oyster|scallop|បង្គា|ក្តាម|មឹក)' THEN '01.1.3.2'
    WHEN canonical_name ~* '(prahok|canned fish|sardine|canned tuna|dried fish|fish sauce|smoked fish|ប្រហុក|ត្រីងៀត|ត្រីខ)' THEN '01.1.3.3'
    WHEN canonical_name ~* '(salmon|tuna|tilapia|snapper|catfish|mackerel|bass|cod|trout|fish|ត្រី)' THEN '01.1.3.1'
    ELSE '01.1.3.1'
END
WHERE coicop_code = '01.1.3';

-- 01.1.4 Milk, cheese & eggs
UPDATE silver.canonical_items
SET coicop_code = CASE
    WHEN canonical_name ~* '(salted egg|century egg|ពងទាប្រៃ)' THEN '01.1.4.2'
    WHEN canonical_name ~* '(egg|eggs|ពងមាន់|ពងទា)' THEN '01.1.4.1'
    WHEN canonical_name ~* '(cheese|cheddar|mozzarella|parmesan|brie|gouda|ឈីស)' THEN '01.1.4.3'
    WHEN canonical_name ~* '(milk|yogurt|yoghurt|butter|cream|dairy|condensed|formula|cerelac|ទឹកដោះគោ)' THEN '01.1.4.3'
    ELSE '01.1.4.3'
END
WHERE coicop_code = '01.1.4';

-- 01.1.5 Oils & fats
UPDATE silver.canonical_items
SET coicop_code = CASE
    WHEN canonical_name ~* '(butter|margarine|ghee|lard|shortening|ខ្លាញ់)' THEN '01.1.5.2'
    ELSE '01.1.5.1'
END
WHERE coicop_code = '01.1.5';

-- 01.1.6 Fruit
UPDATE silver.canonical_items
SET coicop_code = CASE
    WHEN canonical_name ~* '(raisin|dried|prune|date|cranberry|freeze dried)' THEN '01.1.6.2'
    WHEN canonical_name ~* '(nut|cashew|almond|walnut|peanut|hazelnut|macadamia|pistachio|seed|sunflower seed|pumpkin seed|chia|flaxseed|គ្រាប់)' THEN '01.1.6.3'
    ELSE '01.1.6.1'
END
WHERE coicop_code = '01.1.6';

-- 01.1.7 Vegetables
UPDATE silver.canonical_items
SET coicop_code = CASE
    WHEN canonical_name ~* '(pickle|pickled|kimchi|canned corn|canned tomato|fermented|ជ្រក់)' THEN '01.1.7.6'
    WHEN canonical_name ~* '(bean|peas|lentil|chickpea|edamame|soybean|sprout|bean sprout|tofu|សណ្តែក|តៅហ៊ូ)' THEN '01.1.7.5'
    WHEN canonical_name ~* '(potato|sweet potato|cassava|taro|yam|ginger|galangal|turmeric|lotus root|onion|shallot|garlic|ដំឡូង|ខ្ញី|រមៀត|ខ្ទឹម)' THEN '01.1.7.4'
    WHEN canonical_name ~* '(carrot|radish|beet|beetroot|turnip|ការ៉ុត|ឆៃថាវ)' THEN '01.1.7.3'
    WHEN canonical_name ~* '(salad|lettuce|cabbage|spinach|kale|morning glory|celery|bok choy|choy sum|leek|parsley|coriander|mint|basil|cilantro|herb|ស្ពៃ|ត្រកួន|ស្លឹក)' THEN '01.1.7.1'
    ELSE '01.1.7.2'
END
WHERE coicop_code = '01.1.7';

-- 01.1.8 Sugar, jam, honey, chocolate and confectionery
UPDATE silver.canonical_items
SET coicop_code = CASE
    WHEN canonical_name ~* '(ice cream|gelato|sorbet|popsicle|magnum|cornetto|haagen|ben & jerry|magnolia|ការ៉េម)' THEN '01.1.8.5'
    WHEN canonical_name ~* '(chocolate|choco|cacao|truffle|praline|kitkat|snickers|m&m|cadbury|hershey|lindt|kinder|ferrero)' THEN '01.1.8.3'
    WHEN canonical_name ~* '(jam|marmalade|honey|spread|nutella|peanut butter|ឃ្មុំ)' THEN '01.1.8.2'
    WHEN canonical_name ~* '(sugar|sweetener|stevia|syrup|ស្ករ)' THEN '01.1.8.1'
    ELSE '01.1.8.4'
END
WHERE coicop_code = '01.1.8';

-- 01.1.9 Other food products n.e.c.
UPDATE silver.canonical_items
SET coicop_code = CASE
    WHEN canonical_name ~* '(baby food|infant food|puree|gerber|baby cereal)' THEN '01.1.9.2'
    WHEN canonical_name ~* '(sauce|dressing|mayonnaise|ketchup|mustard|vinegar|soy sauce|oyster sauce|fish sauce|chili sauce|hot sauce|salt|black pepper|white pepper|msg|seasoning|spice|bouillon|stock|knorr|maggi|curry paste|ទឹកត្រី|ទឹកស៊ីអ៊ីវ|អំបិល|ម្រេច|ម្សៅស៊ុប)' THEN '01.1.9.1'
    ELSE '01.1.9.9'
END
WHERE coicop_code = '01.1.9';

-- 01.2.1 Coffee, tea & cocoa
UPDATE silver.canonical_items
SET coicop_code = CASE
    WHEN canonical_name ~* '(cocoa|milo|ovomaltine|ovaltine|chocolate drink)' THEN '01.2.1.3'
    WHEN canonical_name ~* '(tea|matcha|herbal|lipton|twinings|chamomile|oolong|តែ)' THEN '01.2.1.2'
    ELSE '01.2.1.1'
END
WHERE coicop_code = '01.2.1';

-- 01.2.2 Mineral waters, soft drinks & juices
UPDATE silver.canonical_items
SET coicop_code = CASE
    WHEN canonical_name ~* '(water|mineral|eau|dasani|aquafina|kulen|evian|volvic|purified|ទឹកសុទ្ធ|ទឹកបរិសុទ្ធ)' THEN '01.2.2.1'
    WHEN canonical_name ~* '(juice|nectar|smoothie|lemonade|orange juice|apple juice|malee|tipco|ទឹកផ្លែឈើ)' THEN '01.2.2.3'
    ELSE '01.2.2.2'
END
WHERE coicop_code = '01.2.2';

-- 2. Division 02: Alcoholic Beverages & Tobacco
UPDATE silver.canonical_items SET coicop_code = '02.1.1.1' WHERE coicop_code = '02.1.1';
UPDATE silver.canonical_items SET coicop_code = '02.1.2.1' WHERE coicop_code = '02.1.2';
UPDATE silver.canonical_items SET coicop_code = '02.1.3.1' WHERE coicop_code = '02.1.3';
UPDATE silver.canonical_items SET coicop_code = '02.2.0.1' WHERE coicop_code IN ('02.2.0', '02.2.1');

-- 3. Division 03: Clothing & Footwear
UPDATE silver.canonical_items
SET coicop_code = CASE
    WHEN canonical_name ~* '(baby|infant|newborn|bodysuit|romper|onesie)' THEN '03.1.2.4'
    WHEN canonical_name ~* '(women|girl|dress|skirt|blouse|bra|lingerie|legging)' THEN '03.1.2.2'
    WHEN canonical_name ~* '(men|boy|shirt|polo|trousers|boxer|brief)' THEN '03.1.2.1'
    ELSE '03.1.2.9'
END
WHERE coicop_code = '03.1.2';

UPDATE silver.canonical_items SET coicop_code = '03.1.3.1' WHERE coicop_code = '03.1.3';
UPDATE silver.canonical_items SET coicop_code = '03.2.1.1' WHERE coicop_code = '03.2.1';

-- 4. Division 04: Housing & Utilities
UPDATE silver.canonical_items SET coicop_code = '04.1.1.1' WHERE coicop_code = '04.1.1';
UPDATE silver.canonical_items SET coicop_code = '04.3.1.1' WHERE coicop_code = '04.3.1';
UPDATE silver.canonical_items SET coicop_code = '04.4.1.1' WHERE coicop_code = '04.4.1';
UPDATE silver.canonical_items SET coicop_code = '04.5.1.1' WHERE coicop_code = '04.5.1';
UPDATE silver.canonical_items SET coicop_code = '04.5.2.1' WHERE coicop_code = '04.5.2';
UPDATE silver.canonical_items SET coicop_code = '04.5.4.1' WHERE coicop_code = '04.5.4';

-- 5. Division 05: Furnishings & Household Maintenance
UPDATE silver.canonical_items SET coicop_code = '05.1.1.1' WHERE coicop_code = '05.1.1';
UPDATE silver.canonical_items SET coicop_code = '05.2.1.1' WHERE coicop_code = '05.2.1';
UPDATE silver.canonical_items SET coicop_code = '05.5.1.1' WHERE coicop_code = '05.5.1';

UPDATE silver.canonical_items
SET coicop_code = CASE
    WHEN canonical_name ~* '(trash|garbage|bag|foil|wrap|sponge|scour|paper towel|tissue|toilet paper|napkin|candle|match)' THEN '05.6.1.2'
    ELSE '05.6.1.1'
END
WHERE coicop_code = '05.6.1';

-- 6. Division 06: Health
UPDATE silver.canonical_items SET coicop_code = '06.1.1.1' WHERE coicop_code = '06.1.1';
UPDATE silver.canonical_items SET coicop_code = '06.1.2.1' WHERE coicop_code = '06.1.2';
UPDATE silver.canonical_items SET coicop_code = '06.2.1.1' WHERE coicop_code = '06.2.1';

-- 7. Division 07: Transport
UPDATE silver.canonical_items SET coicop_code = '07.1.1.1' WHERE coicop_code = '07.1.1';
UPDATE silver.canonical_items SET coicop_code = '07.1.2.1' WHERE coicop_code = '07.1.2';
UPDATE silver.canonical_items
SET coicop_code = CASE
    WHEN canonical_name ~* '(diesel|gasoil|ម៉ាស៊ូត)' THEN '07.2.2.2'
    WHEN canonical_name ~* '(lubricant|engine oil|motor oil|ប្រេងម៉ាស៊ីន)' THEN '07.2.2.3'
    ELSE '07.2.2.1'
END
WHERE coicop_code = '07.2.2';
UPDATE silver.canonical_items SET coicop_code = '07.2.3.1' WHERE coicop_code = '07.2.3';
UPDATE silver.canonical_items SET coicop_code = '07.3.2.1' WHERE coicop_code = '07.3.2';

-- 8. Division 08: Communication
UPDATE silver.canonical_items SET coicop_code = '08.2.0.1' WHERE coicop_code = '08.2.0';
UPDATE silver.canonical_items SET coicop_code = '08.3.0.1' WHERE coicop_code = '08.3.0';

-- 9. Division 09: Recreation & Culture
UPDATE silver.canonical_items SET coicop_code = '09.1.1.1' WHERE coicop_code = '09.1.1';
UPDATE silver.canonical_items SET coicop_code = '09.1.3.1' WHERE coicop_code = '09.1.3';
UPDATE silver.canonical_items
SET coicop_code = CASE
    WHEN canonical_name ~* '(dog|cat|pet|puppy|kitten|whiskas|pedigree|royal canin|me-o|smartheart|leash|litter|សត្វ)' THEN '09.3.1.1'
    ELSE '09.3.1.2'
END
WHERE coicop_code = '09.3.1';
UPDATE silver.canonical_items SET coicop_code = '09.5.1.1' WHERE coicop_code = '09.5.1';

-- 10. Division 10: Education
UPDATE silver.canonical_items SET coicop_code = '10.1.0.1' WHERE coicop_code = '10.1.0';

-- 11. Division 11: Restaurants & Hotels
UPDATE silver.canonical_items SET coicop_code = '11.1.1.1' WHERE coicop_code = '11.1.1';
UPDATE silver.canonical_items SET coicop_code = '11.2.0.1' WHERE coicop_code = '11.2.0';

-- 12. Division 12: Miscellaneous Goods & Services
UPDATE silver.canonical_items SET coicop_code = '12.1.1.1' WHERE coicop_code = '12.1.1';
UPDATE silver.canonical_items SET coicop_code = '12.1.3.1' WHERE coicop_code = '12.1.3';
UPDATE silver.canonical_items SET coicop_code = '12.3.1.1' WHERE coicop_code = '12.3.1';
UPDATE silver.canonical_items SET coicop_code = '12.3.2.1' WHERE coicop_code = '12.3.2';

-- 13. Upgrade any remaining 4-digit standard codes (DD.G.C -> DD.G.C.1)
UPDATE silver.canonical_items
SET coicop_code = coicop_code || '.1'
WHERE coicop_code ~ '^[0-9]{2}\.[0-9]\.[0-9]$';
"""

def main():
    conn_str = get_database_url().replace("postgresql+psycopg2://", "postgresql://", 1)
    conn_str = conn_str.replace("@postgres:", "@localhost:")

    log.info("Connecting to PostgreSQL to reclassify all canonical items into 5-digit COICOP 2018...")
    conn = psycopg2.connect(conn_str)
    try:
        with conn.cursor() as cur:
            cur.execute(SQL_RECLASSIFICATION)
            conn.commit()
            log.info("✅ Successfully executed 5-digit COICOP 2018 reclassification!")

            # Check new distribution of 5-digit vs 4-digit codes
            cur.execute("""
                SELECT 
                    CASE 
                        WHEN LENGTH(coicop_code) - LENGTH(REPLACE(coicop_code, '.', '')) >= 3 THEN '5-digit (COICOP 2018)'
                        WHEN LENGTH(coicop_code) - LENGTH(REPLACE(coicop_code, '.', '')) = 2 THEN '4-digit (COICOP 1999)'
                        ELSE 'other'
                    END as code_format,
                    COUNT(*) as count
                FROM silver.canonical_items
                GROUP BY 1
                ORDER BY count DESC;
            """)
            summary_rows = cur.fetchall()
            log.info("📊 COICOP Code Format Distribution:")
            for fmt, cnt in summary_rows:
                log.info(f"   • {fmt}: {cnt:,} items")

            cur.execute("""
                SELECT coicop_code, COUNT(*) as cnt
                FROM silver.canonical_items
                WHERE LENGTH(coicop_code) >= 8
                GROUP BY coicop_code
                ORDER BY cnt DESC
                LIMIT 25;
            """)
            top_codes = cur.fetchall()
            log.info("🏆 Top 25 5-Digit COICOP Subclasses in canonical_items:")
            for code, cnt in top_codes:
                log.info(f"   • {code}: {cnt:,} items")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
