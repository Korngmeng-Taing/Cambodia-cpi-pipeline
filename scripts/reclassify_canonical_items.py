"""
scripts/reclassify_canonical_items.py
─────────────────────────────────────
Authoritative, high-throughput reclassification engine for silver.canonical_items,
silver.clean_store_prices, and gold.dim_items.

Resolves catalog products across UN COICOP 2018 12 divisions and
granular 5-digit subclasses according to the Cambodia NIS CPI basket:
  Tier 1: Single-Category Pure Store Purity Locks (PPWSA, EDC, Fuel, Telecom)
  Tier 2: Real Estate & Housing Listings (Khmer24, Realestate)
  Tier 3: Dedicated Pharmacy Store Rules (with grocery/cosmetic passthrough)
  Tier 4: Motorbike Apparel & Gear Rules (Khmer Moto apparel -> 03)
  Tier 5: Critical Category Exception Traps:
          - Food Vinegars vs Cleaning Vinegars (01.1.9 vs 05.6.1)
          - Baby Nutrition: Formula (01.1.4), Cereals/Rusks (01.1.1), Purees (01.1.9)
          - Japanese "Bourbon" Brand Snacks (01.1.8 / 01.1.1)
          - "Camel" Brand Nuts & Snacks (01.1.8)
          - Scented Candles & Candle Holders (05.6.1 / 05.5.1)
          - Cooking Hot Pot Broths/Bases, Pot Pies, Bagels, Bowl Noodles (01.1.9 / 01.1.1)
          - Condoms & Sanitary Protection (12.1.3)
          - Household Cleaning Products (even if fruit/lemon/citrus scented) (05.6.1)
          - Electric Fans & Appliances (05.3.1)
  Tier 6: Supermarket Domain Disqualifications (Supermarkets cannot sell hotel stays or housing)
  Tier 7: Hard Lexical Category Rules (Toys, Stationery, Sports, Pet, Pharma, Clothing, Alcohol, Tobacco)
  Tier 8: Food & Non-Alcoholic Beverage Subclasses (01.1.x & 01.2.x)
  Tier 9: Safe Preservation & Groceries Fallback
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

# Stores that are multi-category retail grocers / hypermarkets / general e-commerce
SUPERMARKET_STORES = {
    "aeon", "aeon3", "delishop", "grab_lucky", "grab_chipmong", "l192"
}

# ── 2. Compiled Lexical Patterns ─────────────────────────────────────────────

# Priority Traps
RE_CLEANING_VINEGAR = re.compile(
    r"\b(cleaning vinegar|household vinegar|vinaigre m[ée]nager|streak free.*vinegar|apta.*vinegar|briochin.*vinegar)\b",
    re.I
)
RE_CULINARY_VINEGAR = re.compile(
    r"\b(apple cider vinegar|cider vinegar|wine vinegar|red wine vinegar|white wine vinegar|"
    r"rice wine vinegar|rice vinegar|balsamic|balsamico|distilled white vinegar|distilled vinegar|"
    r"malt vinegar|grape vinegar|vinaigre|vinegar)\b",
    re.I
)
RE_COOKING_WINE = re.compile(r"\b(cooking wine|mirin|shaoxing|sake cooking|rice wine for cooking)\b", re.I)
RE_FRENCH_FRIES = re.compile(r"\b(french fries|crinkle cut fries|shoestring fries|fries 6mm|potato fries|straight cut fries)\b", re.I)

# Baby Nutrition & Care
RE_BABY_FORMULA = re.compile(
    r"\b(infant formula|baby formula|follow[- ]up formula|growing up formula|milk powder|"
    r"dumex|dulac|dugro|bubs goat|bubs organic|wakodo lebens|meiji hohoemi|meiji step|"
    r"similac gain|similac mum|pediasure|enfagrow|nan pro|s-26|illuma|alula)\b",
    re.I
)
RE_BABY_CEREAL = re.compile(
    r"\b(baby cereal|infant cereal|milna baby biscuit|milna biscuit|baby biscuit|baby rusks|"
    r"rice rusks|baby bites|promina baby cereal|promina|cerelac|bledina|baby porridge|"
    r"milna rice puff|milna puffs|puffs organic.*months)\b",
    re.I
)
RE_BABY_PUREE = re.compile(
    r"\b(baby puree|milna fruit puree|puree.*squeeze|fruit puree.*months|fruit puree.*baby|"
    r"rafferty's garden|baby food jar|strained baby food)\b",
    re.I
)
RE_BABY_DIAPERS = re.compile(
    r"\b(diaper|diapers|pampers|mamy poko|huggies|baby wipes|nappy|nappies)\b",
    re.I
)
RE_BABY_TOILETRIES = re.compile(
    r"\b(baby lotion|baby wash|baby shampoo|baby bath|baby oil|baby powder|talcum powder)\b",
    re.I
)

# Japanese Bourbon Brand Snacks & Camel Brand Nuts
RE_BOURBON_SNACK = re.compile(
    r"\bbourbon\s*(petit|alfort|roanne|blanc|chocochip|cracker|biscuit|cookie|wafer|rice cracker|okoge|agemaru|vanilla|soy sauce)\b|\bbourbon petit\b",
    re.I
)
RE_CAMEL_NUTS = re.compile(
    r"\bcamel\b.*\b(nut|nuts|peanut|peanuts|cashew|cashews|almond|almonds|cracker|crackers|mixed nuts|crunchy|anchovies|revive|bounce|sugar)\b|"
    r"\b(peanut cracker|cashew roasted|power revive|power bounce|peanut sugar|peanut & anchovies).*\bcamel\b",
    re.I
)

# Candles & Air Fresheners
RE_CANDLE_HOLDERS = re.compile(r"\b(candle holder|candleholder|candelabra|candle stand|candle tray)\b", re.I)
RE_CANDLES = re.compile(
    r"\b(scented candle|votive candle|tea light candle|aromatherapy candle|birthday candle|"
    r"essential oils candle|candle|candles|votive candles)\b",
    re.I
)

# Culinary Hot Pot, Pot Pies, Bagels, Bowl Noodles
RE_HOT_POT_FOOD = re.compile(
    r"\b(hot pot|hotpot)\b.*\b(base|soup|broth|seasoning|sauce|dipping|paste|instant|spices|broth|bouillon)\b|"
    r"\b(soup base|dipping sauce|broth).*\b(hot pot|hotpot)\b|"
    r"\b(instant hot pot|clear oil hot pot|spicy hot pot|beef hot pot|sichuan hot pot|haidilao hot pot)\b",
    re.I
)
RE_POT_PIE = re.compile(r"\b(pot pie|chicken pot pie|beef pot pie|turkey pot pie)\b", re.I)
RE_BOWL_NOODLE = re.compile(r"\b(bowl noodle|noodle bowl|instant bowl noodle|bowl noodle soup|ramen bowl|udon bowl)\b", re.I)
RE_BAGEL = re.compile(r"\b(bagel|bagels)\b", re.I)

# Sanitary Protection & Contraceptives
RE_SANITARY = re.compile(
    r"\b(sanitary pad|sanitary pads|sanitary napkin|sanitary napkins|pantyliner|panty liner|"
    r"pantyliners|panty liners|tampon|tampons|cindi overnight|cindi panty|kotex|laurier|sofym|libresse)\b",
    re.I
)
RE_CONDOMS = re.compile(r"\b(condom|condoms|durex|okamoto)\b", re.I)

# Toys, Games & Hobbies (09.3.1)
RE_TOYS = re.compile(
    r"\b(toy|toys|lego|puzzle|puzzles|water gun|squirt water|bubble machine|ukulele|doll|dolls|"
    r"plush|blind box|robot|robots|slime|play set|play-doh|nerf|board game|diecast|action figure|"
    r"barbie|drone|remote control car|r/c car|building blocks|playmat|baby three mini|vivistar|"
    r"engineering truck|cat king's workplace|cream cady|noli's rosemary|spin master|hot wheels|"
    r"prank toy|yoyo|magic sand|marbles|pretend play|doctor set|kitchen set toy|makeup set toy)\b",
    re.I
)

# Stationery, Books & Office Supplies (NIS Cambodia CPI: 09.5.1)
RE_STATIONERY = re.compile(
    r"\b(notebook|notebooks|exercise book|pencil|pencils|colored pencils|water color pencils|"
    r"crayons|crayola|ballpen|ball pen|gel pen|roller pen|highlighter|marker|markers|eraser|"
    r"pencil case|sharpener|stapler|staples|paper a4|copy paper|sticky notes|sketch book|"
    r"drawing pad|binder|file folder|ruler|faber-castell|skribe-on|carrying pouch_a6|correction tape|"
    r"geometry set|protractor|whiteboard|calculator|textbook|school book|reading book)\b",
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
    r"dog treats|cat treats|pet shampoo|dog leash|cat toy|churu|ganador|puppy food|kitten food)\b",
    re.I
)

# Household Cleaning, Detergents & Paper (05.6.1)
RE_HOUSEHOLD_CLEAN = re.compile(
    r"\b(pop up tissue|facial tissue|toilet paper|toilet roll|kitchen towel|paper napkin|tissues|"
    r"laundry detergent|washing powder|liquid detergent|dishwashing|dishwash|floor cleaner|"
    r"toilet cleaner|bathroom cleaner|bleach|disinfectant|fabric softener|fabric conditioner|downy|comfort|sunlight|"
    r"attack|magiclean|lix|trash bag|garbage bag|scouring pad|sponge|mop|broom|air freshener|"
    r"little trees|insect spray|mosquito coil|baygon|raid|battery|batteries|alkaline battery|maxell|"
    r"glass cleaner|toilet brush|scouring sponge|citric acid electrolyzed water cleaner)\b",
    re.I
)

# Kitchenware, Cookware & Tableware (05.5.1 / 05.1.1)
RE_KITCHENWARE = re.compile(
    r"\b(frying pan|saucepan|cookware|cooking pot|stock pot|two-flavor hot pot|stainless steel hot pot.*cookware|"
    r"hot pot cooker|plate|plates|spoon|spoons|fork|forks|knife|knives|cutlery|chopsticks|"
    r"whisk|whisks|pepper grinder|salt grinder|automatic grinder|tongs|spatula|ladle|"
    r"thermos|vacuum flask|mug|mugs|drinking glass|shot glass|food container|strainer|"
    r"lunch box|tupperware|faucet|water filter|immersion heater|water electric boiler|tefal|bienvenue|"
    r"water bottle|squeeze bottle|measuring cup|basting brush|pastry brush|oil brush|tablecloth|table cloth|"
    r"baking pan|pizza pan|cake mold|baking dish|grill brush|coffee machine|coffee mill|hand-cranked pepper mill|"
    r"sauce ladle|soup ladle|cheese cover|cheese bell|vegetable mill|fruit press|rice ladle|sauce whisk)\b",
    re.I
)

# Household Appliances (05.3.1)
RE_APPLIANCES = re.compile(
    r"\b(refrigerator|fridge|washing machine|microwave|blender|rice cooker|air fryer|toaster|"
    r"electric kettle|vacuum cleaner|steam iron|clothes iron|dry iron|flat iron|electric fan|stand fan|floor fan|desk fan|cooling mini fan)\b",
    re.I
)

# Phone & Mobile Accessories (08.2.0)
RE_PHONE_ACC = re.compile(
    r"\b(phone case|phone cover|phone screen|screen protector|tempered glass|charging cable|usb cable|"
    r"usb-c|lightning cable|phone charger|power bank|earphone|earphones|headphone|headphones|earbuds|"
    r"phone holder|phone stand|mobile stand|tablet stand|ipad stand|phone radiator|cooling fan.*phone|wireless cooling fan)\b",
    re.I
)

# Camping & Recreation Gear (09.3.2)
RE_CAMPING = re.compile(
    r"\b(tent|sleeping bag|camping|camp kit|fire starter|flint fire|magnesium bar|survival kit)\b",
    re.I
)

# Decorative Furnishings & Joss Paper (05.1.1 / 05.6.1)
RE_DECOR = re.compile(
    r"\b(artificial flower|branches of|alocasia|aroma diffuser|flower pot|decorative|joss paper|gold joss paper)\b",
    re.I
)

# Hair Care (12.1.1)
RE_HAIR_CARE = re.compile(
    r"\b(shampoo|hair conditioner|hair mask|hair dye|hair treatment|hair styling|hair wax|"
    r"hair gel|pomade|haircut|hair clipper|hair trimmer|pantene|head & shoulders|sunsilk|clear shampoo|"
    r"l'oreal hair|tresemme)\b",
    re.I
)

# Personal Care, Hygiene & Cosmetics (12.1.3 & 12.1.1)
RE_PERSONAL_CARE = re.compile(
    r"\b(body wash|shower gel|shower foam|shower cream|bath soap|bar soap|soap bar|soap tube|"
    r"facial cleanser|face wash|face scrub|face cream|face moisturizer|body lotion|hand cream|"
    r"skin cream|serum|sunscreen|sunblock|spf50|spf 50|uv essence|cleansing oil|cleansing foam|"
    r"peeling gel|ampoule|ampoul|fragrance mist|hair vitamin|blot paper|cleansing brush|"
    r"makeup tool|face brush|makeup brush|facial brush|beauty tool|lip and eye remover|eye remover|"
    r"biore|nivea|vaseline|cetaphil|cerave|bioderma|hada labo|hadalabo|farmstay|dr\. somchai|aveeno|"
    r"purell|eucerin|uriage|cica farm|cica|oral care|toothpaste|tooth paste|toothbrush|tooth brush|"
    r"mouthwash|colgate|sensodyne|darlie|pepsodent|deodorant|roll-on|roll on|body spray|perfume|"
    r"eau de toilette|cologne|edp|edt|valentino|moschino|shiseido|razor|razors|shaver|shaving foam|"
    r"shaving cream|gillette|lipstick|lip balm|lipice|mascara|eyeliner|foundation|cosmetics|"
    r"skincare|facial spray|facial mist)\b",
    re.I
)

# Medicines & Pharmaceuticals (06.1.1 / 06.1.2)
RE_PHARMA = re.compile(
    r"\b(paracetamol|panadol|ibuprofen|kinal|aspirin|antibiotic|cough syrup|cold medicine|"
    r"allergy relief|antihistamine|eye drops|rohto|nasclean|saline solution|normal saline|"
    r"tiger balm|naga balm|massage oil balm|red pepper balm|antiseptic|betadine|bandages|"
    r"plaster|thermometer|blood pressure|vitamin c|multivitamin|fish oil|zinc tablet|phcare|septyl|"
    r"efferalgan|dafalgan|diclofenac)\b",
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
    r"bra|socks|pajamas|swimwear|vest|cardigan|pleated skirt|crop top|riding suit)\b",
    re.I
)

# Food Subclasses (01.1.x & 01.2.x)
RE_MEAT = re.compile(
    r"\b(chicken|chicken breast|chicken drumstick|chicken wing|whole chicken|roast chicken|"
    r"fried chicken|pork|pork belly|pork ribs|pork chop|ground pork|minced pork|beef|beef steak|"
    r"beef slice|ground beef|minced beef|veal|lamb|mutton|duck|turkey|sausage|sausages|hotdog|"
    r"hot dog|bacon|ham|prosciutto|meatball|meatballs|pork ball|beef ball|saucisse seche|salami|steak meal)\b",
    re.I
)

RE_SEAFOOD = re.compile(
    r"\b(salmon|salmon fillet|tuna|sea bass|catfish|tilapia|mackerel|sardine|sardines|shrimp|"
    r"shrimps|prawn|prawns|crab|crabs|squid|squids|cuttlefish|octopus|lobster|oyster|oysters|"
    r"mussel|mussels|clam|clams|dried fish|dried shrimp|canned fish|canned tuna|fish ball|"
    r"fish cake|fish fillet|seafood mix|anchovy|saba fish|sashimi)\b",
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
    r"extra virgin olive oil|coconut oil|sesame oil|corn oil|peanut oil|shortening|lard|olive pomace oil)\b",
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
    r"pickled cucumber|pickles|pesto)\b",
    re.I
)

RE_SWEETS = re.compile(
    r"\b(chocolate|chocolates|choco|dark chocolate|milk chocolate|white chocolate|candy|candies|"
    r"marshmallow|marshmallows|mashmallow|gummy|gummies|gummy bear|jelly|jellies|ice jelly|"
    r"cookies|cookie|biscuit|biscuits|wafer|wafers|tartlet|tartlets|cake|cakes|brownie|pie|"
    r"choco pie|sugar|white sugar|brown sugar|honey|sweetener|jam|strawberry jam|caramel|"
    r"chips|potato chips|crisps|doritos|pringles|lays|snack|snacks|rice crackers|rice pops|"
    r"kinder bueno|ferrero rocher|hershey|kisses|m&m|kitkat|snickers|toblerone|nutella|"
    r"loacker|matilde vicenzi|orion|prawn crackers|energy bar|protein bar|maple syrup)\b",
    re.I
)

RE_SEASONING = re.compile(
    r"\b(seasoning|seasoning powder|chicken powder|pork powder|bouillon|chicken bouillon|"
    r"knorr|knat|romeas|ajinomoto|msg|salt|table salt|pink salt|sea salt|black pepper|white pepper|"
    r"peppercorn|soy sauce|fish sauce|oyster sauce|ketchup|tomato ketchup|mayo|mayonnaise|"
    r"mustard|dijon mustard|curry paste|chili sauce|hot sauce|sriracha|dressing|"
    r"salad dressing|bbq sauce|deep fried powder|crispy powder|crispy deep fried|chili powder|"
    r"paprika|cinnamon|turmeric|cumin|coriander powder|stock cube|bolognese|pasta sauce|marinade|"
    r"broth|kelp broth|bone broth|dashi|soup base)\b",
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
    r"nutri-c|cordial|syrup drink|ginger ale|bitter lemon)\b",
    re.I
)

RE_CEREALS = re.compile(
    r"\b(rice|jasmine rice|fragrant rice|sticky rice|brown rice|white rice|basmati|bread|"
    r"baguette|toast|sandwich bread|croissant|croissants|buns|bun|noodles|instant noodles|"
    r"mama noodles|ramen|udon|soba|vermicelli|rice noodle|pasta|spaghetti|macaroni|penne|"
    r"fusilli|lasagna|ravioli|flour|wheat flour|all purpose flour|cake flour|oats|rolled oats|"
    r"oatmeal|muesli|granola|cereals|cereal|corn flakes|vitalia muesli|eric kayser|"
    r"pizza|sushi|onigiri|bento|takoyaki|dumpling|dumplings)\b",
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
    Authoritative classification ladder for UN COICOP 2018 & NIS Cambodia CPI.
    Returns (coicop_division, coicop_code, method).
    """
    clean_name = name.strip() if name else ""
    clean_name_lower = clean_name.lower()
    stores_set = {s.lower().strip() for s in stores if s}
    
    # Filter out deceptive or multi-department umbrella category strings
    umbrella_labels = {
        "grocery", 
        "general retail > apparel & household goods", 
        "fashion & beauty", 
        "supermarket",
        "general retail"
    }
    clean_cats = [c.lower().strip() for c in categories if c and c.lower().strip() not in umbrella_labels]
    cat_str = " ".join(clean_cats)

    # ──────────────────────────────────────────────────────────────────────────
    # Tier 1: Single-Category Pure Store Domain Purity Locks
    # ──────────────────────────────────────────────────────────────────────────
    if stores_set and stores_set.issubset(set(PURE_STORE_MAP.keys())):
        first_store = list(stores_set)[0]
        div, code = PURE_STORE_MAP[first_store]
        # Special case: LPG gas cylinder at new_gasoline
        if first_store in ("new_gasoline", "gasoline") and "lpg" in clean_name_lower:
            return "04", "04.5.2", "store_purity"
        return div, code, "store_purity"

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
            w in clean_name_lower for w in ["villa", "condo", "apartment", "shophouse", "for rent", "ជួល", "បន្ទប់"]
        ):
            return "04", "04.1.1", "housing_rule"

    # ──────────────────────────────────────────────────────────────────────────
    # Tier 3: Motorcycle Apparel & Gear at Khmer Moto
    # ──────────────────────────────────────────────────────────────────────────
    if "khmermoto" in stores_set:
        if any(w in clean_name_lower for w in ["jacket", "shirt", "suit", "jersey", "hoodie", "sleeve"]):
            return "03", "03.1.2", "riding_garments"
        if any(w in clean_name_lower for w in ["shoes", "boots", "boot", "footwear"]):
            return "03", "03.2.1", "riding_footwear"
        if any(w in clean_name_lower for w in ["gloves", "glove"]):
            return "03", "03.1.3", "riding_gloves"
        if any(w in clean_name_lower for w in ["helmet", "goggle", "helmets", "goggles"]):
            return "07", "07.2.1", "riding_helmet_accessories"
        if any(w in clean_name_lower for w in ["honda", "suzuki", "yamaha", "scooter", "125cc", "150cc", "250cc"]):
            return "07", "07.1.2", "motorcycle_vehicle"

    # ──────────────────────────────────────────────────────────────────────────
    # Tier 4: Critical Category Exception Traps (Run Before Broad Exclusions)
    # ──────────────────────────────────────────────────────────────────────────

    # 0. iPhone-branded items (08.2.0) — always phones, never fruit or household
    if "iphone" in clean_name_lower or re.search(r'\bphone\b.*\biphone\b|\biphone\b.*\bphone\b', clean_name_lower):
        return "08", "08.2.0", "iphone_rule"

    # 1. Laundry Detergent / Dishwashing Liquid (05.6.1 / 05.5.1) — always household
    if re.search(r'\b(laundry detergent|dishwashing liquid|dish washing liquid)\b', clean_name_lower):
        return "05", "05.6.1", "laundry_detergent_rule"
    if "palmolive" in clean_name_lower and any(w in clean_name_lower for w in ["dish", "liquid", "soap"]):
        return "05", "05.6.1", "dishwashing_liquid_rule"

    # 2. Toothpaste (12.1.3) — always personal care, never pharma or stationery
    if re.search(r'\btoothpaste\b', clean_name_lower):
        return "12", "12.1.3", "toothpaste_rule"

    # 3. Food Vinegars vs Cleaning Vinegars
    if RE_CLEANING_VINEGAR.search(clean_name):
        return "05", "05.6.1", "cleaning_vinegar_rule"
    if RE_CULINARY_VINEGAR.search(clean_name):
        return "01", "01.1.9", "culinary_vinegar_rule"

    # 2. Japanese "Bourbon" Brand Snacks & Biscuits (Intercept before RE_SPIRITS)
    if RE_BOURBON_SNACK.search(clean_name):
        return "01", "01.1.8", "bourbon_snack_rule"

    # 3. "Camel" Brand Nuts & Crackers (Intercept before RE_TOBACCO)
    if RE_CAMEL_NUTS.search(clean_name):
        return "01", "01.1.8", "camel_nuts_rule"

    # 4. Scented Candles & Candle Holders (Intercept before fruit/dairy/tea/alcohol)
    if RE_CANDLE_HOLDERS.search(clean_name):
        return "05", "05.5.1", "candle_holder_rule"
    if RE_CANDLES.search(clean_name):
        return "05", "05.6.1", "candle_rule"

    # 5. Baby Nutrition & Food Staples (Intercept before cosmetics/personal care)
    if RE_BABY_FORMULA.search(clean_name):
        return "01", "01.1.4", "baby_formula_rule"
    if RE_BABY_CEREAL.search(clean_name):
        return "01", "01.1.1", "baby_cereal_rule"
    if RE_BABY_PUREE.search(clean_name):
        return "01", "01.1.9", "baby_puree_rule"

    # 6. Culinary Hot Pot Broths/Bases, Pot Pies, Bagels & Bowl Noodles (Intercept before RE_KITCHENWARE)
    if (("hot pot" in clean_name_lower or "hotpot" in clean_name_lower) and not any(
        w in clean_name_lower for w in ["cooker", "pan", "pot cooker", "pot pan", "grill", "stove", "induction", "ladle", "spoon", "tableware", "cookware"]
    )) or RE_HOT_POT_FOOD.search(clean_name):
        return "01", "01.1.9", "hot_pot_food_rule"
    if RE_POT_PIE.search(clean_name):
        return "01", "01.1.1", "pot_pie_rule"
    if RE_BOWL_NOODLE.search(clean_name):
        return "01", "01.1.1", "bowl_noodle_rule"
    if RE_BAGEL.search(clean_name):
        return "01", "01.1.1", "bagel_rule"

    # 7. Sanitary Protection & Contraceptives (Intercept before hospitality/clothing)
    if RE_SANITARY.search(clean_name):
        return "12", "12.1.3", "sanitary_rule"
    if RE_CONDOMS.search(clean_name):
        return "12", "12.1.3", "condom_rule"

    # 8. Baby Diapers & Toiletries
    if RE_BABY_DIAPERS.search(clean_name):
        return "12", "12.1.3", "diaper_rule"
    if RE_BABY_TOILETRIES.search(clean_name):
        return "12", "12.1.3", "baby_toiletries_rule"

    # 9. Household Cleaning Products (even if fruit/lemon scented)
    if RE_HOUSEHOLD_CLEAN.search(clean_name):
        return "05", "05.6.1", "household_clean_rule"

    # 10. Household Appliances (Fans, irons, kettles, rice cookers)
    if RE_APPLIANCES.search(clean_name) and not any(
        w in clean_name_lower for w in [
            "pastry", "pastries", "pop tart", "cereal", "supplement", "vitamin", "kitkat", "milo",
            "cleaner", "cleaning", "tablet", "powder", "descaler", "fresh-keeping", "cling film",
            "storage box", "organizer", "tray", "drawer", "toy", "puzzle", "piggy bank", "iron starch",
            "starch", "wrought iron", "iron box"
        ]
    ):
        return "05", "05.3.1", "appliance_rule"

    # ──────────────────────────────────────────────────────────────────────────
    # Tier 5: Dedicated Pharmacy Stores (communitypharma, grab_ucare)
    # ──────────────────────────────────────────────────────────────────────────
    if stores_set and stores_set.issubset(PHARMACY_STORES):
        # Beverage & Mineral Water at pharmacy
        if any(w in clean_name_lower for w in ["eau kulen", "kulen", "dasani", "vital", "mineral water", "drinking water"]):
            return "01", "01.2.2", "pharma_bottled_water"
        # Snacks, energy bars, syrups, honey at pharmacy
        if any(w in clean_name_lower for w in ["energy bar", "protein bar", "lecka", "honey", "maple syrup", "gummies", "candy"]):
            return "01", "01.1.8", "pharma_snack_nutrition"
        # Hair care at pharmacy
        if RE_HAIR_CARE.search(clean_name):
            return "12", "12.1.1", "pharma_haircare"
        # Cosmetics & Skincare at pharmacy
        if RE_PERSONAL_CARE.search(clean_name) and not any(
            w in clean_name_lower for w in ["antiseptic", "betadine", "balm", "pain", "medical", "treatment", "plaster", "sterile", "ointment", "eye drops", "ear drops", "nasal", "saline"]
        ):
            return "12", "12.1.3", "pharma_cosmetics"
        # Medical Equipment / Diagnostics
        if any(w in clean_name_lower for w in ["thermometer", "blood pressure", "test kit", "mask", "syringe", "strip", "compress"]):
            if "bbq" not in clean_name_lower and "smoker" not in clean_name_lower and "grill" not in clean_name_lower:
                return "06", "06.1.3", "pharma_equipment"
        # Default for Pure Pharmacy: Division 06 (06.1.1 Medicines)
        return "06", "06.1.1", "pharmacy_store_lock"

    # ──────────────────────────────────────────────────────────────────────────
    # Tier 6: Non-Food Hard Exclusions (Toys, Stationery, Sports, Household, Pharma)
    # ──────────────────────────────────────────────────────────────────────────

    # Culinary BBQ Thermometer Trap
    if "thermometer" in clean_name_lower and any(w in clean_name_lower for w in ["bbq", "smoker", "grill", "meat", "cooking", "kitchen", "dial"]):
        return "05", "05.5.1", "kitchen_thermometer_rule"

    # Toys & Hobbies (09.3.1)
    if RE_TOYS.search(clean_name) or "toy" in cat_str or "toys" in cat_str:
        return "09", "09.3.1", "toy_rule"

    # Stationery, Books & Office Supplies (NIS Cambodia CPI: 09.5.1)
    if RE_STATIONERY.search(clean_name) or any(w in cat_str for w in ["stationery", "school supplies", "notebook", "pencil"]):
        return "09", "09.5.1", "stationery_rule"

    # Sporting Equipment (09.3.2)
    if RE_SPORTS.search(clean_name) or "sport" in cat_str:
        return "09", "09.3.2", "sports_rule"

    # Camping & Recreation Gear (09.3.2)
    if RE_CAMPING.search(clean_name):
        return "09", "09.3.2", "camping_rule"

    # Pet Food & Supplies (09.3.4)
    if RE_PETS.search(clean_name) or "pet" in cat_str:
        return "09", "09.3.4", "pet_rule"

    # Phone & Mobile Accessories (08.2.0)
    if RE_PHONE_ACC.search(clean_name):
        return "08", "08.2.0", "phone_accessories_rule"

    # Decorative Items & Joss Paper (05.1.1 / 05.6.1)
    if RE_DECOR.search(clean_name):
        if "joss paper" in clean_name_lower:
            return "05", "05.6.1", "joss_paper_rule"
        return "05", "05.1.1", "decor_rule"

    # Pharmacy / Medicines (06.1.1 / 06.1.2)
    if RE_PHARMA.search(clean_name):
        return "06", "06.1.2", "pharma_rule"

    # Hair Care (12.1.1)
    if RE_HAIR_CARE.search(clean_name) or "hair care" in cat_str:
        return "12", "12.1.1", "haircare_rule"

    # Personal Care, Hygiene, Cosmetics & Diapers (12.1.3)
    if RE_PERSONAL_CARE.search(clean_name) or any(
        k in cat_str for k in ["personal care", "skincare", "oral care", "bath", "baby care"]
    ):
        return "12", "12.1.3", "personal_care_rule"

    # Kitchenware & Cookware (05.5.1 / 05.1.1)
    if RE_KITCHENWARE.search(clean_name) or any(
        k in cat_str for k in ["cookware", "kitchenware", "tableware", "dining ware"]
    ):
        return "05", "05.5.1", "kitchenware_rule"

    # Footwear (03.2.1)
    if (RE_FOOTWEAR.search(clean_name) or "shoes" in cat_str or "footwear" in cat_str) and not any(
        w in clean_name_lower for w in ["brush", "cleaner", "polish", "rack", "horn", "deodorant", "spray"]
    ):
        return "03", "03.2.1", "footwear_rule"

    # Clothing & Apparel (03.1.2)
    clothing_cat_keywords = [
        "men's clothing", "women's clothing", "kids clothing", "children's clothing",
        "ladies wear", "men's wear", "fashion & apparel > men's clothing",
        "fashion & apparel > women's clothing", "clothing & footwear"
    ]
    if (RE_CLOTHING.search(clean_name) or any(k in cat_str for k in clothing_cat_keywords)) and not any(
        w in clean_name_lower for w in [
            "tablecloth", "table cloth", "pastry brush", "oil brush", "basting brush", "grill brush",
            "water bottle", "squeeze bottle", "measuring cup", "coffee machine", "remover", "cleanser",
            "peeling gel", "ampoul", "fragrance mist", "perfume", "edp", "diffuser", "phone stand",
            "table stand", "cake mold", "pizza pan", "pan non-stick", "blot paper"
        ]
    ):
        return "03", "03.1.2", "clothing_rule"

    # Alcoholic Beverages (02.1.x) & Tobacco (02.2.0)
    # Check beer with negative exclusions
    if (RE_BEER.search(clean_name) or "beer" in cat_str or "cider" in cat_str) and not any(
        w in clean_name_lower for w in ["vinegar", "cider vinegar", "non-alcoholic", "alcohol-free", "0.0%", "ginger ale", "beer batter", "chips"]
    ):
        return "02", "02.1.3", "beer_rule"

    # Check wine with negative exclusions
    if (RE_WINE.search(clean_name) or "wine" in cat_str or "champagne" in cat_str) and not any(
        w in clean_name_lower for w in ["vinegar", "wine vinegar", "wine glass", "wine opener", "bolognese", "pasta sauce", "chips", "crisps", "candle"]
    ):
        return "02", "02.1.2", "wine_rule"

    # Check spirits with negative exclusions
    if (RE_SPIRITS.search(clean_name) or "spirit" in cat_str or "liquor" in cat_str) and not any(
        w in clean_name_lower for w in ["bourbon petit", "bourbon & oak", "petit", "vanilla", "candle", "cracker", "biscuit"]
    ):
        return "02", "02.1.1", "spirits_rule"

    # Check tobacco with negative exclusions
    if (RE_TOBACCO.search(clean_name) or "tobacco" in cat_str or "cigarette" in cat_str) and not any(
        w in clean_name_lower for w in ["camel", "anti-tobacco", "nut", "peanut", "cashew", "candle"]
    ):
        return "02", "02.2.0", "tobacco_rule"

    # ──────────────────────────────────────────────────────────────────────────
    # Tier 7: Food & Non-Alcoholic Beverages (Division 01 Subclasses)
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

    # 2. Seasonings, Condiments, Spices, Sauces (01.1.9)
    if RE_SEASONING.search(clean_name) or any(k in cat_str for k in ["seasoning", "condiment", "spice", "sauce", "pantry"]):
        return "01", "01.1.9", "seasoning_rule"

    # 3. Confectionery, Sugar, Chocolates, Snacks, Nuts, Chips (01.1.8)
    if RE_SWEETS.search(clean_name) or any(k in cat_str for k in ["confectionery", "chocolate", "candy", "sweets", "biscuit", "cookie", "chips", "snack"]):
        return "01", "01.1.8", "sweets_rule"

    # 4. Bottled Waters, Soft Drinks, Juices (01.2.2)
    if RE_BEVERAGES.search(clean_name) or any(k in cat_str for k in ["beverage", "drink", "water", "soft drink", "juice"]):
        return "01", "01.2.2", "beverage_rule"

    # 5. Cooking Oils & Fats (01.1.5)
    cooking_oil_cats = ["cooking oil", "vegetable oil", "olive oil", "oils & fats", "edible oil"]
    if RE_OIL.search(clean_name) or any(k in cat_str for k in cooking_oil_cats):
        return "01", "01.1.5", "oil_rule"

    # 6. Milk, Cheese, Butter & Eggs (01.1.4)
    dairy_cats = ["dairy", "cheese", "eggs", "butter", "yogurt"]
    if RE_DAIRY.search(clean_name) or any(k in cat_str for k in dairy_cats) or (
        "milk" in cat_str and not any(w in cat_str for w in ["body milk", "cleansing milk", "milk protein"])
    ):
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

    # 10. Fresh & Preserved Vegetables (01.1.7)
    if RE_VEG.search(clean_name) or any(k in cat_str for k in ["vegetable", "produce", "salad"]):
        return "01", "01.1.7", "vegetable_rule"

    # 11. Bread, Cereals, Rice, Grains, Flour, Pasta (01.1.1)
    if RE_CEREALS.search(clean_name) or any(k in cat_str for k in ["bakery", "bread", "cereal", "rice", "noodle", "pasta", "flour"]):
        return "01", "01.1.1", "cereal_rule"

    # ──────────────────────────────────────────────────────────────────────────
    # Tier 8: Supermarket Domain Disqualifications
    # ──────────────────────────────────────────────────────────────────────────
    # Supermarkets cannot sell hotel stays, restaurant dining, or municipal utilities
    if stores_set.issubset(SUPERMARKET_STORES):
        # Disqualify from Division 11 (Hospitality)
        if current_div == "11":
            if any(w in clean_name_lower for w in ["sushi", "bento", "onigiri", "karaage", "pizza", "meal", "porridge"]):
                return "01", "01.1.1", "disqualified_to_bakery_cereal"
            if any(w in clean_name_lower for w in ["steak", "beef", "chicken", "pork", "fish"]):
                return "01", "01.1.2", "disqualified_to_meat"
            if any(w in clean_name_lower for w in ["strainer", "mat", "place mat", "food storage", "wrap"]):
                return "05", "05.5.1", "disqualified_to_kitchen"
            if any(w in clean_name_lower for w in ["top", "shirt", "pants", "dress", "clothing"]):
                return "03", "03.1.2", "disqualified_to_clothing"
            if any(w in clean_name_lower for w in ["panty", "liner", "pad", "condom", "clip"]):
                return "12", "12.1.3", "disqualified_to_toiletries"
            return "01", "01.1.9", "disqualified_11_to_groceries"

        # Disqualify from Division 04 (Housing/Rentals)
        if current_div == "04":
            if any(w in clean_name_lower for w in ["plate", "pan", "pot", "glass", "mug", "table"]):
                return "05", "05.5.1", "disqualified_to_kitchen"
            if any(w in clean_name_lower for w in ["battery", "clean", "wash"]):
                return "05", "05.6.1", "disqualified_to_clean"
            return "01", "01.1.9", "disqualified_04_to_groceries"

        # Disqualify bogus Division 02 items
        if current_div == "02" and any(w in clean_name_lower for w in ["bagel", "cracker", "chips", "vinegar", "candle", "sauce", "bolognese", "candy", "gum"]):
            if "bagel" in clean_name_lower:
                return "01", "01.1.1", "bagel_rule"
            if "vinegar" in clean_name_lower:
                return "01", "01.1.9", "culinary_vinegar_rule"
            if "candle" in clean_name_lower:
                return "05", "05.6.1", "candle_rule"
            return "01", "01.1.8", "disqualified_02_to_snacks"

        # Disqualify bogus Division 06 items (Food/syrups/water at supermarket)
        if current_div == "06" and any(w in clean_name_lower for w in ["water", "syrup", "energy bar", "honey", "juice", "tea", "coffee"]):
            if "water" in clean_name_lower:
                return "01", "01.2.2", "disqualified_06_to_water"
            return "01", "01.1.8", "disqualified_06_to_sweets"

    # ──────────────────────────────────────────────────────────────────────────
    # Tier 9: Safe Preservation & Groceries Fallback
    # ──────────────────────────────────────────────────────────────────────────
    # If the previous classification was valid, does not violate any store domain,
    # and has not been identified as an anomalous pattern, preserve it.
    if current_div and current_code and current_div != "UNCLASSIFIED" and current_code != "UNCLASSIFIED":
        # Disallow preservation of known illegal cross-contaminations:
        if not (current_div == "11" and stores_set.issubset(SUPERMARKET_STORES)) and \
           not (current_div == "04" and stores_set.issubset(SUPERMARKET_STORES)) and \
           not (current_div == "02" and any(w in clean_name_lower for w in ["bagel", "vinegar", "camel", "bourbon petit", "candle"])) and \
           not (current_div == "10" and RE_STATIONERY.search(clean_name)) and \
           not (current_div == "05" and any(w in clean_name_lower for w in ["hot pot", "hotpot", "broth", "kelp broth", "pot pie", "bowl noodle", "cereal", "kitkat", "milo"])) and \
           not (current_div == "03" and any(w in clean_name_lower for w in ["water bottle", "squeeze bottle", "measuring cup", "coffee machine", "tablecloth", "pastry brush", "oil brush", "grill brush", "pan", "remover", "peeling gel", "ampoul", "diffuser", "phone stand", "blot paper"])):
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
