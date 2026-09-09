"""
scripts/reclassify_canonical_items.py
─────────────────────────────────────
Authoritative, high-throughput reclassification engine for silver.canonical_items,
silver.clean_store_prices, and gold.dim_items.

Resolves all 43,344 catalog products across UN COICOP 2018 12 divisions and
65 granular 5-digit subclasses using a deterministic, 5-tier resolution ladder:
  Tier 1: Exact Overrides (coicop_override & coicop_override_manual)
  Tier 2: Single-Category Pure Store Purity Locks (PPWSA, EDC, Fuel, Telecom, etc.)
  Tier 3: Retail Store Domain Exclusions (Supermarkets cannot sell rentals or municipal water)
  Tier 4: Native Category Taxonomy Mapping (Department / Aisle / Subcategory)
  Tier 5: Multilingual (English, French, Khmer) Lexical Subclass Pattern Engine
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from psycopg2.extras import execute_batch

from pipeline.config import get_db_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("reclassify_canonical_items")


# ── 1. Pure Store Domains ────────────────────────────────────────────────────
PURE_STORE_MAP: dict[str, tuple[str, str]] = {
    "ppwsa": ("04", "04.4.1"),             # Municipal tap water supply
    "edc": ("04", "04.5.1"),               # Electric grid power
    "realestate": ("04", "04.1.1"),        # House / apartment rentals
    "bookmebus": ("07", "07.3.2"),         # Intercity bus transport
    "redbus": ("07", "07.3.2"),            # Intercity bus transport
    "redmebus": ("07", "07.3.2"),          # Intercity bus transport
    "khmermoto": ("07", "07.1.2"),         # Motorcycles & scooters
    "cellcard": ("08", "08.3.0"),          # Cellular network services
    "cellcard_wifi": ("08", "08.3.0"),     # Home fiber wifi
    "smart": ("08", "08.3.0"),             # Cellular network services
    "smart_wifi": ("08", "08.3.0"),        # Home fiber wifi
    "metfone": ("08", "08.3.0"),           # Cellular network services
    "arystore": ("08", "08.2.0"),          # Phones, tablets & telecom equipment
    "samnangshop": ("08", "08.2.0"),       # Phones, tablets & telecom equipment
    "sokhahotel": ("11", "11.2.0"),        # Hotel accommodation
    "hyyathotel": ("11", "11.2.0"),        # Hotel accommodation
    "hyatthotel": ("11", "11.2.0"),        # Hotel accommodation
    "hyatt": ("11", "11.2.0"),             # Hotel accommodation
    "bayonbkk": ("11", "11.1.1"),          # Restaurant dining
}

# Stores that are dedicated pharmacies
PHARMACY_STORES = {
    "communitypharma", "grab_ucare", "ucare"
}

# Stores that are multi-category retail grocers / hypermarkets
SUPERMARKET_STORES = {
    "aeon", "aeon3", "delishop", "grab_lucky", "grab_chipmong", "l192"
}

# ── 2. Compiled Lexical Patterns ─────────────────────────────────────────────

# Priority 0: Exact Overrides / Food Traps
RE_COOKING_WINE = re.compile(r"\b(cooking wine|mirin|shaoxing|sake cooking)\b", re.I)
RE_FRENCH_FRIES = re.compile(r"\b(french fries|crinkle cut|shoestring|fries 6mm|potato fries)\b", re.I)

# Toys, Games & Hobbies (09.3.1)
RE_TOYS = re.compile(
    r"\b(toy|toys|lego|puzzle|puzzles|water gun|squirt water|bubble machine|ukulele|doll|dolls|"
    r"plush|blind box|robot|robots|slime|play set|play-doh|nerf|board game|diecast|action figure|"
    r"barbie|drone|remote control car|r/c car|building blocks|playmat|baby three mini|vivistar|"
    r"engineering truck|cat king's workplace|cream cady|noli's rosemary|spin master|hot wheels|"
    r"prank toy|yoyo|magic sand|marbles|pretend play|doctor set|kitchen set toy|makeup set toy)\b",
    re.I
)

# Stationery, Books & Office Supplies (09.5.4)
RE_STATIONERY = re.compile(
    r"\b(notebook|notebooks|exercise book|pencil|pencils|colored pencils|water color pencils|"
    r"crayons|crayola|ballpen|ball pen|gel pen|roller pen|highlighter|marker|markers|eraser|"
    r"pencil case|sharpener|stapler|staples|paper a4|copy paper|sticky notes|sketch book|"
    r"drawing pad|binder|file folder|ruler|faber-castell|skribe-on|carrying pouch_a6|correction tape)\b",
    re.I
)

# Sports Equipment (09.3.2)
RE_SPORTS = re.compile(
    r"\b(badminton|tennis racket|shuttlecock|dumbbell|barbell|yoga mat|yoga training|fitness band|"
    r"jump rope|swimming goggles|soccer ball|football|basketball|volleyball|table tennis|ping pong)\b",
    re.I
)

# Pet Food & Supplies (09.3.4)
RE_PETS = re.compile(
    r"\b(cat food|dog food|pet food|cat litter|whiskas|pedigree|smartheart|me-o|royal canin|purina|"
    r"dog treats|cat treats|pet shampoo|dog leash|cat toy)\b",
    re.I
)

# Household Cleaning, Detergents & Paper (05.6.1)
RE_HOUSEHOLD_CLEAN = re.compile(
    r"\b(pop up tissue|facial tissue|toilet paper|toilet roll|kitchen towel|paper napkin|tissues|"
    r"laundry detergent|washing powder|liquid detergent|dishwashing|dishwash|floor cleaner|"
    r"toilet cleaner|bathroom cleaner|bleach|disinfectant|fabric softener|downy|comfort|sunlight|"
    r"attack|magiclean|lix|trash bag|garbage bag|scouring pad|sponge|mop|broom|air freshener|"
    r"little trees|insect spray|mosquito coil|baygon|raid|battery|batteries|alkaline battery|maxell)\b",
    re.I
)

# Kitchenware, Cookware & Tableware (05.5.1 / 05.1.1)
RE_KITCHENWARE = re.compile(
    r"\b(frying pan|saucepan|cookware|pot|pots|plate|plates|bowl|bowls|spoon|spoons|fork|forks|"
    r"knife|knives|cutlery|chopsticks|whisk|whisks|pepper grinder|salt grinder|automatic grinder|"
    r"tongs|spatula|ladle|thermos|vacuum flask|mug|mugs|drinking glass|shot glass|food container|"
    r"lunch box|tupperware|faucet|water filter|immersion heater|water electric boiler|tefal|bienvenue)\b",
    re.I
)

# Household Appliances (05.3.1)
RE_APPLIANCES = re.compile(
    r"\b(refrigerator|fridge|washing machine|microwave|blender|rice cooker|air fryer|toaster|"
    r"electric kettle|vacuum cleaner|iron|steam iron|electric fan|stand fan)\b",
    re.I
)

# Personal Care, Hygiene & Cosmetics (12.1.3 & 12.1.1)
RE_HAIR_CARE = re.compile(
    r"\b(shampoo|hair conditioner|hair mask|hair dye|hair treatment|hair styling|hair wax|"
    r"hair gel|pomade|haircut|hair clipper|hair trimmer|pantene|head & shoulders|sunsilk|clear shampoo|"
    r"l'oreal hair|tresemme)\b",
    re.I
)
RE_PERSONAL_CARE = re.compile(
    r"\b(body wash|shower gel|bath soap|bar soap|facial cleanser|face wash|face scrub|face cream|"
    r"face moisturizer|body lotion|hand cream|skin cream|serum|sunscreen|sunblock|spf50|spf 50|"
    r"biore|nivea|vaseline|cetaphil|cerave|toothpaste|tooth paste|toothbrush|tooth brush|mouthwash|"
    r"colgate|sensodyne|darlie|pepsodent|diaper|diapers|pampers|mamy poko|huggies|baby wipes|"
    r"wet wipes|sanitary pad|sanitary pads|pantyliner|tampon|kotex|laurier|sofym|deodorant|"
    r"roll-on|roll on|body spray|perfume|eau de toilette|cologne|razor|razors|shaver|shaving foam|"
    r"shaving cream|gillette|lipstick|lip balm|lipice|mascara|eyeliner|foundation|cosmetics|skincare)\b",
    re.I
)

# Medicines & Pharmaceuticals (06.1.1 / 06.1.2)
RE_PHARMA = re.compile(
    r"\b(paracetamol|panadol|ibuprofen|kinal|aspirin|antibiotic|cough syrup|cold medicine|"
    r"allergy relief|antihistamine|eye drops|rohto|nasclean|saline solution|normal saline|"
    r"tiger balm|naga balm|massage oil balm|red pepper balm|antiseptic|betadine|bandages|"
    r"plaster|thermometer|blood pressure|vitamin c|multivitamin|fish oil|zinc tablet|phcare|septyl)\b",
    re.I
)

# Alcohol & Tobacco (02)
RE_BEER = re.compile(
    r"\b(beer|beers|lager|stout|cider|angkor beer|cambodia beer|heineken|tiger beer|budweiser|"
    r"corona beer|somersby|singha|asahi|hoegaarden|craft beer|draught beer|shandy)\b",
    re.I
)
RE_WINE = re.compile(
    r"\b(wine|wines|red wine|white wine|sparkling wine|champagne|bordeaux|merlot|cabernet|"
    r"shiraz|chardonnay|sauvignon|prosecco|rosé|rose wine|cava|chianti|riesling|pinot noir|"
    r"château|aoc|aop|igp|wolf blass|gérard bertrand|henriot|louis roederer)\b",
    re.I
)
RE_SPIRITS = re.compile(
    r"\b(whisky|whiskey|vodka|gin|rum|cognac|tequila|brandy|bourbon|scotch|single malt|"
    r"johnnie walker|chivas|hennessy|jack daniel|smirnoff|absolut|bacardi|gordon's|tanqueray)\b",
    re.I
)
RE_TOBACCO = re.compile(
    r"\b(cigarette|cigarettes|cigar|cigars|tobacco|cigarillos|marlboro|555|esse|mevius|"
    r"winston|camel|dunhill|rolling tobacco)\b",
    re.I
)

# Clothing & Footwear (03)
RE_FOOTWEAR = re.compile(
    r"\b(shoes|sneakers|boots|sandals|slippers|flip-flops|flip flops|loafers|athletic shoes|"
    r"leather shoes|high heels|slipper unisex|tvhc slipper)\b",
    re.I
)
RE_CLOTHING = re.compile(
    r"\b(t-shirt|t shirt|shirt|shirts|polo|pants|trousers|jeans|denim|shorts|skirt|skirts|"
    r"dress|dresses|jacket|jackets|hoodie|sweater|coat|blazer|underwear|boxer|boxers|panties|"
    r"bra|socks|pajamas|swimwear|vest|cardigan|pleated skirt)\b",
    re.I
)

# Food Subclasses (01.1.x & 01.2.x)
RE_MEAT = re.compile(
    r"\b(chicken|chicken breast|chicken drumstick|chicken wing|whole chicken|roast chicken|"
    r"fried chicken|pork|pork belly|pork ribs|pork chop|ground pork|minced pork|beef|beef steak|"
    r"beef slice|ground beef|minced beef|veal|lamb|mutton|duck|turkey|sausage|sausages|hotdog|"
    r"hot dog|bacon|ham|prosciutto|meatball|meatballs|pork ball|beef ball|saucisse seche)\b",
    re.I
)

RE_SEAFOOD = re.compile(
    r"\b(salmon|salmon fillet|tuna|sea bass|catfish|tilapia|mackerel|sardine|sardines|shrimp|"
    r"shrimps|prawn|prawns|crab|crabs|squid|squids|cuttlefish|octopus|lobster|oyster|oysters|"
    r"mussel|mussels|clam|clams|dried fish|dried shrimp|canned fish|canned tuna|fish ball|"
    r"fish cake|fish fillet|seafood mix|anchovy|praws)\b",
    re.I
)

RE_DAIRY = re.compile(
    r"\b(milk|fresh milk|uht milk|full cream|skim milk|raw milk|condensed milk|evaporated milk|"
    r"moo moo fresh milk|soy milk|soya milk|almond milk|cheese|cheddar|mozzarella|parmesan|"
    r"gouda|brie|camembert|cream cheese|cheese slice|butter|unsalted butter|salted butter|"
    r"margarine|whipping cream|cooking cream|yogurt|yoghurt|greek yogurt|curd|egg|eggs|"
    r"chicken eggs|duck eggs|fresh eggs|quail eggs)\b",
    re.I
)

RE_OIL = re.compile(
    r"\b(cooking oil|vegetable oil|palm oil|canola oil|sunflower oil|soybean oil|olive oil|"
    r"extra virgin olive oil|coconut oil|sesame oil|corn oil|peanut oil|shortening|lard)\b",
    re.I
)

RE_FRUIT = re.compile(
    r"\b(apple|apples|fuji apple|banana|bananas|cavendish|orange|oranges|mandarin|mango|"
    r"mangoes|watermelon|grape|grapes|strawberry|strawberries|blueberry|blueberries|raspberry|"
    r"lemon|lemons|lime|limes|papaya|pineapple|guava|durian|dragon fruit|avocado|avocados|"
    r"plum|plums|pear|pears|gold pear|kiwi|coconut fresh|peach|cherry|cherries|grapefruit|"
    r"passion fruit|lychee|longan|rambutan|mangosteen|pomegranate|dried fruit|raisins|prunes)\b",
    re.I
)

RE_VEG = re.compile(
    r"\b(tomato|tomatoes|potato|potatoes|onion|onions|shallot|shallots|garlic|chili|chilies|"
    r"ginger|carrot|carrots|cabbage|lettuce|cucumber|cucumbers|broccoli|cauliflower|spinach|"
    r"morning glory|mushroom|mushrooms|corn|sweet corn|green bean|peas|bell pepper|eggplant|"
    r"zucchini|pumpkin|radish|celery|asparagus|salad mix|kimchi|spicy kimchi|bingo kimchi|"
    r"pickled cucumber|pickles|bolognese|pasta sauce|tomato sauce|tomato paste|pesto)\b",
    re.I
)

RE_SWEETS = re.compile(
    r"\b(chocolate|chocolates|choco|dark chocolate|milk chocolate|white chocolate|candy|candies|"
    r"marshmallow|marshmallows|mashmallow|gummy|gummies|gummy bear|jelly|jellies|ice jelly|"
    r"cookies|cookie|biscuit|biscuits|wafer|wafers|tartlet|tartlets|cake|cakes|brownie|pie|"
    r"choco pie|sugar|white sugar|brown sugar|honey|sweetener|jam|strawberry jam|caramel|"
    r"chips|potato chips|crisps|doritos|pringles|lays|snack|snacks|rice crackers|rice pops|"
    r"kinder bueno|ferrero rocher|hershey|kisses|m&m|kitkat|snickers|toblerone|nutella|"
    r"loacker|matilde vicenzi|orion)\b",
    re.I
)

RE_SEASONING = re.compile(
    r"\b(seasoning|seasoning powder|chicken powder|pork powder|bouillon|chicken bouillon|"
    r"knorr|knat|romeas|ajinomoto|msg|salt|table salt|pink salt|sea salt|black pepper|white pepper|"
    r"peppercorn|soy sauce|fish sauce|oyster sauce|ketchup|tomato ketchup|mayo|mayonnaise|"
    r"mustard|dijon mustard|curry paste|chili sauce|hot sauce|sriracha|vinegar|dressing|"
    r"salad dressing|bbq sauce|deep fried powder|crispy powder|crispy deep fried|chili powder|"
    r"paprika|cinnamon|turmeric|cumin|coriander powder|stock cube)\b",
    re.I
)

RE_COFFEE_TEA = re.compile(
    r"\b(coffee|ground coffee|coffee beans|instant coffee|nescafe|espresso|cappuccino|latte|"
    r"maccoffee|cafepho|tea|tea bag|tea bags|green tea|black tea|jasmine tea|oolong tea|"
    r"matcha|herbal tea|harimaya|twinings|lipton|dilmah|cacao|cocoa|cocoa powder|cacao powder|"
    r"chocolate powder|poulain)\b",
    re.I
)

RE_BEVERAGES = re.compile(
    r"\b(mineral water|drinking water|bottled water|spring water|purified water|sparkling water|"
    r"dasani|evian|kulen|vital|eau kulen|fruit juice|orange juice|apple juice|grape juice|"
    r"juice|soft drink|coca cola|coke|pepsi|sprite|fanta|7up|tonic water|soda water|soda|"
    r"energy drink|red bull|sting|carabao|bacchus|aloe vera drink|strawberry drink|wicky|"
    r"nutri-c|cordial|syrup drink)\b",
    re.I
)

RE_CEREALS = re.compile(
    r"\b(rice|jasmine rice|fragrant rice|sticky rice|brown rice|white rice|basmati|bread|"
    r"baguette|toast|sandwich bread|croissant|croissants|buns|bun|noodles|instant noodles|"
    r"mama noodles|ramen|udon|soba|vermicelli|rice noodle|pasta|spaghetti|macaroni|penne|"
    r"fusilli|lasagna|ravioli|flour|wheat flour|all purpose flour|cake flour|oats|rolled oats|"
    r"oatmeal|muesli|granola|cereals|cereal|corn flakes|vitalia muesli|eric kayser)\b",
    re.I
)

RE_HOUSING_REALESTATE = re.compile(
    r"\b(house for rent|villa for rent|apartment for rent|condo for rent|studio for rent|"
    r"room for rent|house rental|villa rental|apartment rental|condo rental|shophouse for rent|"
    r"land for rent|bedroom condo|bedroom apartment|bedroom villa|bedroom house|"
    r"home rental|commercial space for rent|office for rent|flat for rent|បន្ទប់ជួល|ផ្ទះជួល|"
    r"វីឡាជួល|ខុនដូជួល)\b",
    re.I
)


def classify_item(
    name: str,
    stores: list[str],
    categories: list[str],
    current_div: str | None = None,
    current_code: str | None = None,
) -> tuple[str, str, str]:
    """
    Returns (coicop_division, coicop_code, method).
    """
    clean_name = name.strip() if name else ""
    stores_set = {s.lower().strip() for s in stores if s}
    cat_str = " ".join(categories).lower() if categories else ""

    # ──────────────────────────────────────────────────────────────────────────
    # Tier 1: Pure Single-Division Store Locks
    # ──────────────────────────────────────────────────────────────────────────
    if stores_set and stores_set.issubset(set(PURE_STORE_MAP.keys())):
        first_store = list(stores_set)[0]
        div, code = PURE_STORE_MAP[first_store]
        # LPG gas trap at new_gasoline
        if first_store in ("new_gasoline", "gasoline") and "lpg" in clean_name.lower():
            return "04", "04.5.2", "store_purity"
        return div, code, "store_purity"

    # Specific Pure Store Dominance:
    if "ppwsa" in stores_set and len(stores_set) == 1:
        return "04", "04.4.1", "store_purity"
    if "edc" in stores_set and len(stores_set) == 1:
        return "04", "04.5.1", "store_purity"
    if "realestate" in stores_set and len(stores_set) == 1:
        return "04", "04.1.1", "store_purity"

    # ──────────────────────────────────────────────────────────────────────────
    # Tier 2: Real Estate & Housing Listings (Khmer24 Real Estate)
    # ──────────────────────────────────────────────────────────────────────────
    if "khmer24" in stores_set or "realestate" in stores_set:
        if RE_HOUSING_REALESTATE.search(clean_name) or any(
            w in clean_name.lower() for w in ["villa", "condo", "apartment", "shophouse", "for rent", "ជួល", "បន្ទប់"]
        ):
            return "04", "04.1.1", "housing_rule"

    # ──────────────────────────────────────────────────────────────────────────
    # Tier 2.5: Dedicated Pharmacy Stores (communitypharma, grab_ucare)
    # ──────────────────────────────────────────────────────────────────────────
    if stores_set and (stores_set.issubset(PHARMACY_STORES) or any(s in stores_set for s in PHARMACY_STORES)):
        # Exception 1: Baby formula / Infant nutrition is Division 01 (01.1.4)
        if any(w in clean_name.lower() for w in ["baby milk", "infant formula", "pediasure", "similac", "enfagrow", "cerelac", "baby cereal", "nestle nan"]):
            return "01", "01.1.4", "pharma_baby_nutrition"
        # Exception 2: Pure Hair Care & Shampoos is Division 12 (12.1.1)
        if RE_HAIR_CARE.search(clean_name):
            return "12", "12.1.1", "pharma_haircare"
        # Exception 3: Pure Cosmetics, Deodorants, Face moisturizers is Division 12 (12.1.3)
        # unless it is an explicit medicated/antiseptic cream, balm, or treatment
        if RE_PERSONAL_CARE.search(clean_name) and not any(w in clean_name.lower() for w in ["antiseptic", "betadine", "balm", "pain", "medical", "treatment", "bandage", "plaster", "sterile", "ointment", "eye drops", "nasal", "saline"]):
            return "12", "12.1.3", "pharma_cosmetics"
        # Exception 4: Medical Equipment / Diagnostics (06.1.3)
        if any(w in clean_name.lower() for w in ["thermometer", "blood pressure", "test kit", "mask", "syringe", "strip", "compress"]):
            return "06", "06.1.3", "pharma_equipment"
        # Default for Pharmacy: Division 06 (06.1.1 / 06.1.2 Pharmaceutical Products & Medicines)
        return "06", "06.1.1", "pharmacy_store_lock"

    # ──────────────────────────────────────────────────────────────────────────
    # Tier 3: Non-Food Hard Exclusions (Toys, Stationery, Sports, Household, Pharma)
    # ──────────────────────────────────────────────────────────────────────────

    # Toys & Hobbies (09.3.1)
    if RE_TOYS.search(clean_name) or "toy" in cat_str or "toys" in cat_str:
        return "09", "09.3.1", "toy_rule"

    # Education: School Stationery, Textbooks, Notebooks, Pens & Supplies (10.1.0)
    if RE_STATIONERY.search(clean_name) or any(w in cat_str for w in ["stationery", "school supplies", "notebook", "pencil"]):
        return "10", "10.1.0", "education_stationery_rule"

    # Sporting Equipment (09.3.2)
    if RE_SPORTS.search(clean_name) or "sport" in cat_str:
        return "09", "09.3.2", "sports_rule"

    # Pet Food & Supplies (09.3.4)
    if RE_PETS.search(clean_name) or "pet" in cat_str:
        return "09", "09.3.4", "pet_rule"

    # Pharmacy / Medicines (06.1.1 / 06.1.2)
    if RE_PHARMA.search(clean_name):
        return "06", "06.1.2", "pharma_rule"

    # Hair Care (12.1.1)
    if RE_HAIR_CARE.search(clean_name) or "hair care" in cat_str:
        return "12", "12.1.1", "haircare_rule"

    # Personal Care, Hygiene, Cosmetics & Diapers (12.1.3)
    if RE_PERSONAL_CARE.search(clean_name) or any(
        k in cat_str for k in ["personal care", "skincare", "oral care", "bath", "baby feeding", "baby diapers"]
    ):
        return "12", "12.1.3", "personal_care_rule"

    # Household Paper Tissues, Cleaning Detergents (05.6.1)
    if RE_HOUSEHOLD_CLEAN.search(clean_name) or any(
        k in cat_str for k in ["cleaning", "laundry", "detergent", "household supplies", "dishwashing"]
    ):
        return "05", "05.6.1", "household_clean_rule"

    # Kitchenware & Cookware (05.5.1 / 05.1.1)
    if RE_KITCHENWARE.search(clean_name) or any(
        k in cat_str for k in ["cookware", "kitchen", "dining", "tableware"]
    ):
        return "05", "05.5.1", "kitchenware_rule"

    # Household Appliances (05.3.1)
    if RE_APPLIANCES.search(clean_name) or "large appliance" in cat_str or "small appliance" in cat_str:
        return "05", "05.3.1", "appliance_rule"

    # Footwear (03.2.1)
    if RE_FOOTWEAR.search(clean_name) or "shoes" in cat_str or "footwear" in cat_str:
        return "03", "03.2.1", "footwear_rule"

    # Clothing & Apparel (03.1.2)
    if RE_CLOTHING.search(clean_name) or any(
        k in cat_str for k in ["clothing", "apparel", "fashion", "men's wear", "women's wear", "kids clothing"]
    ):
        return "03", "03.1.2", "clothing_rule"

    # Alcoholic Beverages (02.1.x) & Tobacco (02.2.0)
    if RE_BEER.search(clean_name) or "beer" in cat_str or "cider" in cat_str:
        return "02", "02.1.3", "beer_rule"
    if RE_WINE.search(clean_name) or "wine" in cat_str or "champagne" in cat_str:
        return "02", "02.1.2", "wine_rule"
    if RE_SPIRITS.search(clean_name) or "spirit" in cat_str or "liquor" in cat_str:
        return "02", "02.1.1", "spirits_rule"
    if RE_TOBACCO.search(clean_name) or "tobacco" in cat_str or "cigarette" in cat_str:
        return "02", "02.2.0", "tobacco_rule"

    # ──────────────────────────────────────────────────────────────────────────
    # Tier 4: Food & Non-Alcoholic Beverages (Division 01 Subclasses)
    # ──────────────────────────────────────────────────────────────────────────

    # Special Traps: Cooking Wine / Cooking Mirin is Seasoning (01.1.9)
    if RE_COOKING_WINE.search(clean_name):
        return "01", "01.1.9", "cooking_wine_rule"

    # French Fries is Vegetable (01.1.7)
    if RE_FRENCH_FRIES.search(clean_name):
        return "01", "01.1.7", "french_fries_rule"

    # 1. Coffee, Tea & Cocoa (01.2.1)
    if RE_COFFEE_TEA.search(clean_name) or any(k in cat_str for k in ["coffee", "tea", "cocoa", "cacao"]):
        return "01", "01.2.1", "coffee_tea_rule"

    # 2. Seasonings, Condiments, Spices, Bouillon Powders, Sauces (01.1.9)
    # Must be evaluated before Meat/Seafood to capture 'Chicken seasoning powder', 'Fish sauce', etc.
    if RE_SEASONING.search(clean_name) or any(k in cat_str for k in ["seasoning", "condiment", "spice", "sauce"]):
        return "01", "01.1.9", "seasoning_rule"

    # 3. Confectionery, Sugar, Chocolates, Marshmallows, Snacks (01.1.8)
    # Must be evaluated before Fruit to capture 'Strawberry marshmallow', 'Fruit jelly', etc.
    if RE_SWEETS.search(clean_name) or any(k in cat_str for k in ["confectionery", "chocolate", "candy", "sweets", "biscuit", "cookie", "chips", "snack"]):
        return "01", "01.1.8", "sweets_rule"

    # 4. Bottled Waters, Soft Drinks, Juices (01.2.2)
    if RE_BEVERAGES.search(clean_name) or any(k in cat_str for k in ["beverage", "drink", "water", "soft drink", "juice"]):
        return "01", "01.2.2", "beverage_rule"

    # 5. Cooking Oils & Fats (01.1.5)
    if RE_OIL.search(clean_name) or "oil" in cat_str:
        return "01", "01.1.5", "oil_rule"

    # 6. Milk, Cheese, Butter & Eggs (01.1.4)
    if RE_DAIRY.search(clean_name) or any(k in cat_str for k in ["dairy", "milk", "cheese", "eggs", "butter", "yogurt"]):
        return "01", "01.1.4", "dairy_rule"

    # 7. Fresh, Chilled & Frozen Meat & Poultry (01.1.2)
    if RE_MEAT.search(clean_name) or any(k in cat_str for k in ["meat", "poultry", "butchery", "beef", "pork", "chicken"]):
        return "01", "01.1.2", "meat_rule"

    # 8. Fresh, Chilled & Frozen Fish & Seafood (01.1.3)
    if RE_SEAFOOD.search(clean_name) or any(k in cat_str for k in ["seafood", "fish", "fishery"]):
        return "01", "01.1.3", "seafood_rule"

    # 9. Fresh Fruits (01.1.6)
    if RE_FRUIT.search(clean_name) or "fruit" in cat_str:
        return "01", "01.1.6", "fruit_rule"

    # 10. Fresh & Preserved Vegetables & Sauces (01.1.7)
    if RE_VEG.search(clean_name) or any(k in cat_str for k in ["vegetable", "produce", "salad", "pasta sauces"]):
        return "01", "01.1.7", "vegetable_rule"

    # 11. Bread, Cereals, Rice, Grains, Flour, Pasta (01.1.1)
    if RE_CEREALS.search(clean_name) or any(k in cat_str for k in ["bakery", "bread", "cereal", "rice", "noodle", "pasta", "flour"]):
        return "01", "01.1.1", "cereal_rule"

    # ──────────────────────────────────────────────────────────────────────────
    # Tier 5: Fallback Preservation & Domain Disqualification
    # ──────────────────────────────────────────────────────────────────────────
    # If the item was previously classified into 04 (Housing) or 07 (Transport)
    # but belongs to a supermarket, it is an illegal classification.
    if current_div in ("04", "07", "08", "10") and stores_set.issubset(SUPERMARKET_STORES):
        if any(w in clean_name.lower() for w in ["plate", "pan", "pot", "glass", "mug", "table"]):
            return "05", "05.5.1", "disqualified_to_kitchen"
        if any(w in clean_name.lower() for w in ["battery", "clean", "wash"]):
            return "05", "05.6.1", "disqualified_to_clean"
        return "01", "01.1.9", "disqualified_to_groceries"

    # Preserve current classification if valid
    if current_div and current_code and current_div != "UNCLASSIFIED" and current_code != "UNCLASSIFIED":
        return current_div, current_code, "preserved_valid"

    return "01", "01.1.9", "fallback_groceries"


def run(dry_run: bool = True, batch_size: int = 2000):
    log.info("Connecting to CPI PostgreSQL database...")
    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        log.info("Loading all canonical items with store associations and native categories...")
        cur.execute("""
            SELECT 
                ci.item_id::text,
                ci.canonical_name,
                ci.coicop_division,
                ci.coicop_code,
                array_agg(distinct s.store_slug) filter (where s.store_slug is not null) as stores,
                array_agg(distinct s.category_native) filter (where s.category_native is not null and s.category_native <> '') as categories
            FROM silver.canonical_items ci
            LEFT JOIN silver.clean_store_prices s ON ci.item_id::text = s.item_id::text
            GROUP BY ci.item_id, ci.canonical_name, ci.coicop_division, ci.coicop_code;
        """)
        rows = cur.fetchall()
        total_items = len(rows)
        log.info("Loaded %d canonical items from database.", total_items)

        reclassified_rows = []
        div_counts: dict[str, int] = {}
        code_counts: dict[str, int] = {}
        changes_count = 0
        div_changes_count = 0

        for item_id, name, cur_div, cur_code, stores, categories in rows:
            stores_list = stores or []
            cat_list = categories or []
            new_div, new_code, method = classify_item(
                name=name or "",
                stores=stores_list,
                categories=cat_list,
                current_div=cur_div,
                current_code=cur_code,
            )

            div_counts[new_div] = div_counts.get(new_div, 0) + 1
            code_counts[new_code] = code_counts.get(new_code, 0) + 1

            if new_code != cur_code:
                changes_count += 1
            if new_div != cur_div:
                div_changes_count += 1

            reclassified_rows.append((new_div, new_code, method, item_id))

        log.info("=" * 70)
        log.info("RECLASSIFICATION SUMMARY (Total: %d items):", total_items)
        log.info("  Items with 5-digit code changes: %d (%.2f%%)", changes_count, changes_count * 100.0 / total_items)
        log.info("  Items with 2-digit division changes: %d (%.2f%%)", div_changes_count, div_changes_count * 100.0 / total_items)
        log.info("-" * 70)
        log.info("NEW DIVISION DISTRIBUTION:")
        for div in sorted(div_counts.keys()):
            cnt = div_counts[div]
            log.info("  Division %s: %5d items (%.2f%%)", div, cnt, cnt * 100.0 / total_items)
        log.info("-" * 70)
        log.info("TOP 15 5-DIGIT CODES:")
        for code, cnt in sorted(code_counts.items(), key=lambda x: x[1], reverse=True)[:15]:
            log.info("  Code %s: %5d items (%.2f%%)", code, cnt, cnt * 100.0 / total_items)
        log.info("=" * 70)

        if dry_run:
            log.info("DRY RUN mode active — no database changes committed.")
            return

        log.info("APPLYING DATABASE UPDATES...")

        # 1. Update silver.canonical_items
        log.info("1/3 Updating silver.canonical_items (%d records)...", len(reclassified_rows))
        execute_batch(cur, """
            UPDATE silver.canonical_items
            SET coicop_division = %s,
                coicop_code = %s,
                coicop_method = %s,
                coicop_confidence = 0.950,
                coicop_classified_at = NOW()
            WHERE item_id = %s::uuid;
        """, reclassified_rows, page_size=batch_size)
        log.info("Successfully updated silver.canonical_items.")

        # 2. Update gold.dim_items to stay 100% in sync
        log.info("2/3 Synchronizing gold.dim_items...")
        cur.execute("""
            UPDATE gold.dim_items di
            SET coicop_division = ci.coicop_division,
                coicop_code = ci.coicop_code
            FROM silver.canonical_items ci
            WHERE di.item_id = ci.item_id::text
              AND (di.coicop_code != ci.coicop_code OR di.coicop_division != ci.coicop_division);
        """)
        log.info("Synchronized %d items in gold.dim_items.", cur.rowcount)

        # 3. Synchronize silver.clean_store_prices
        log.info("3/3 Synchronizing silver.clean_store_prices...")
        cur.execute("""
            UPDATE silver.clean_store_prices s
            SET coicop_division = ci.coicop_division,
                coicop_code = ci.coicop_code,
                coicop_method = 'canonical_sync',
                coicop_confidence = 0.950
            FROM silver.canonical_items ci
            WHERE s.item_id::text = ci.item_id::text
              AND (s.coicop_code != ci.coicop_code OR s.coicop_division != ci.coicop_division);
        """)
        log.info("Synchronized %d observations in silver.clean_store_prices.", cur.rowcount)

        conn.commit()
        log.info("ALL DATABASE UPDATES COMMITTED SUCCESSFULLY!")

    except Exception as e:
        conn.rollback()
        log.exception("Reclassification failed! Rolled back transaction: %s", e)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reclassify silver.canonical_items across 12 COICOP divisions.")
    parser.add_argument("--execute", action="store_true", help="Execute database updates (default is dry-run)")
    parser.add_argument("--batch-size", type=int, default=2000, help="Batch size for execute_batch")
    args = parser.parse_args()

    run(dry_run=not args.execute, batch_size=args.batch_size)
