"""
scripts/fix_classification_anomalies.py
────────────────────────────────────────
Remediates audited classification anomalies in silver.canonical_items:
  1. Fixes 17 legacy Division 13 items -> Division 12 (12.1.3 Personal Care).
  2. Fixes ~357 pet food & accessories misclassified under Division 01/05 -> Division 09 (09.3.1 Pets).
  3. Fixes personal care hygiene products misclassified under Food/Communication/Appliances -> Division 12 (12.1.3).
  4. Fixes Maggie Beer brand bone broth misclassified as alcoholic beer -> Division 01 (01.1.9).
  5. Resolves '.unclassified' codes to valid NIS 4-digit class codes where possible.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from pipeline.config import get_db_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def remediate_classifications() -> None:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # 1. Remap Division 13 to Division 12
            logger.info("1. Remapping legacy Division 13 items to Division 12...")
            cur.execute(
                """
                UPDATE silver.canonical_items
                SET 
                    coicop_division = '12',
                    coicop_code = '12.1.3',
                    coicop_method = 'remediated_audit_div12',
                    coicop_confidence = 0.9500,
                    coicop_classified_at = NOW()
                WHERE coicop_division = '13' OR coicop_code LIKE '13.%';
                """
            )
            div13_count = cur.rowcount
            logger.info("   -> Remapped %d items from Division 13 to Division 12.", div13_count)

            # 2. Fix Pet Food & Pet Accessories (Royal Canin, Pedigree, Purina, etc.)
            logger.info("2. Fixing Pet Food & Accessories misclassified under human food or cleaning...")
            cur.execute(
                """
                UPDATE silver.canonical_items
                SET 
                    coicop_division = '09',
                    coicop_code = '09.3.1',
                    coicop_method = 'remediated_audit_pet_food',
                    coicop_confidence = 0.9500,
                    coicop_classified_at = NOW()
                WHERE (
                    canonical_name ~* '\\y(dog food|cat food|pet food|cat litter|puppy kibble|kitten pouch|pedigree|whiskas|royal canin|purina one|smartheart|me-o|cesar dog|inaba ciao)\\y'
                    OR (canonical_name ~* '\\y(chunks in gravy|thin slices in gravy|kibbles)\\y' AND canonical_name ~* '\\y(royal canin|pedigree|purina|whiskas|smartheart)\\y')
                )
                AND coicop_division != '09';
                """
            )
            pet_count = cur.rowcount
            logger.info("   -> Fixed %d pet food items to Division 09 (09.3.1).", pet_count)

            # 3. Fix Personal Care & Hygiene misclassified as Food, Cleaning, or Tech
            logger.info("3. Fixing Personal Care & Hygiene products...")
            cur.execute(
                """
                UPDATE silver.canonical_items
                SET 
                    coicop_division = '12',
                    coicop_code = '12.1.3',
                    coicop_method = 'remediated_audit_personal_care',
                    coicop_confidence = 0.9500,
                    coicop_classified_at = NOW()
                WHERE (
                    canonical_name ~* '\\y(shampoo|shower gel|body wash|face wash|facial wash|micellar|sunscreen|moisturizer|cleansing foam|toner|hair conditioner|hand wash|antiperspirant|deodorant|cleansing gel)\\y'
                )
                AND canonical_name !~* '(empty bottle|refillable bottle|dog|cat|pet|refrigerator deodorant|ice sleeve)'
                AND coicop_division NOT IN ('12');
                """
            )
            personal_count = cur.rowcount
            logger.info("   -> Fixed %d personal care items to Division 12 (12.1.3).", personal_count)

            # 4. Fix Maggie Beer / Beerenberg false alcohol classifications
            logger.info("4. Fixing Maggie Beer & Beerenberg non-alcoholic products...")
            cur.execute(
                """
                UPDATE silver.canonical_items
                SET 
                    coicop_division = '01',
                    coicop_code = '01.1.9',
                    coicop_method = 'remediated_audit_culinary',
                    coicop_confidence = 0.9500,
                    coicop_classified_at = NOW()
                WHERE canonical_name ~* '\\y(maggie beer)\\y'
                  AND coicop_division = '02';
                """
            )
            maggie_count = cur.rowcount

            cur.execute(
                """
                UPDATE silver.canonical_items
                SET 
                    coicop_division = '01',
                    coicop_code = '01.1.9',
                    coicop_method = 'remediated_audit_culinary',
                    coicop_confidence = 0.9500,
                    coicop_classified_at = NOW()
                WHERE canonical_name ~* '\\y(beerenberg)\\y'
                  AND canonical_name ~* '\\y(sauce|jam|chutney|relish)\\y'
                  AND coicop_division = '02';
                """
            )
            beerenberg_count = cur.rowcount
            logger.info("   -> Fixed %d Maggie Beer / Beerenberg items back to Division 01.", maggie_count + beerenberg_count)

            # 5. Resolve remaining .unclassified codes by assigning safe group-level defaults
            logger.info("5. Resolving .unclassified codes to canonical 4-digit class defaults...")
            unclass_map = {
                "01.unclassified": ("01", "01.1.9"),
                "02.unclassified": ("02", "02.1.3"),
                "03.unclassified": ("03", "03.1.2"),
                "04.unclassified": ("04", "04.1.1"),
                "05.unclassified": ("05", "05.6.1"),
                "06.unclassified": ("06", "06.1.1"),
                "07.unclassified": ("07", "07.2.2"),
                "08.unclassified": ("08", "08.2.0"),
                "09.unclassified": ("09", "09.3.1"),
                "11.unclassified": ("11", "11.1.1"),
                "12.unclassified": ("12", "12.1.3"),
            }
            resolved_unclass = 0
            for unclass_code, (div, target_code) in unclass_map.items():
                cur.execute(
                    """
                    UPDATE silver.canonical_items
                    SET 
                        coicop_code = %s,
                        coicop_division = %s,
                        coicop_method = 'remediated_unclassified_default',
                        coicop_confidence = 0.8500,
                        coicop_classified_at = NOW()
                    WHERE coicop_code = %s;
                    """,
                    (target_code, div, unclass_code),
                )
                resolved_unclass += cur.rowcount
            logger.info("   -> Resolved %d .unclassified items to default 4-digit class codes.", resolved_unclass)

            conn.commit()
            logger.info("✅ All classification remediations committed successfully.")
    finally:
        conn.close()


if __name__ == "__main__":
    remediate_classifications()
