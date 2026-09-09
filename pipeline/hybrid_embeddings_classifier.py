"""
pipeline/hybrid_embeddings_classifier.py
────────────────────────────────────────
Hybrid Multilingual Vector Embeddings + Gemini Pro/Flash COICOP Classifier
(BIS Project Spectrum Architecture).

Categorizes newly discovered products across UN COICOP 2018 2-digit divisions (01-12)
and granular 4-digit/5-digit classes via:
1. Tier 1 Human Overrides
2. Tier 2 Single-Category Store Domain Purity (15 pure stores: Gas, Telecom, etc.)
3. Tier 3 Sub-Millisecond Vector Cosine against 4-Digit & 12-Division Multilingual Reference Spaces
4. Tier 4 Batched Gemini Pro/Flash LLM for ambiguous items (<0.72) + Postgres Memoization
"""

from __future__ import annotations

import json
import logging
import os
import re
import numpy as np
from typing import Any

from pipeline.key_pool import get_key_pool
from pipeline.text_clean import is_khmer_text, extract_khmer_tokens, KHMER_COMPOUNDS

try:
    from google import genai
    from google.genai import types as genai_types
    HAS_NEW_GENAI = True
    HAS_GENAI = True
except ImportError:
    genai = None
    genai_types = None
    HAS_NEW_GENAI = False
    try:
        import google.generativeai as genai
        HAS_GENAI = True
    except ImportError:  # pragma: no cover
        genai = None
        HAS_GENAI = False

try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:  # pragma: no cover
    SentenceTransformer = None
    HAS_SENTENCE_TRANSFORMERS = False

log = logging.getLogger(__name__)

EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-2")
LLM_MODEL = os.getenv("GEMINI_PRO_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
LOCAL_FALLBACK_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# Single-Category Pure Stores (Instant SQL / Python Assignment)
PURE_STORE_MAP: dict[str, tuple[str, str]] = {
    "new_gasoline": ("07", "07.2.2"),
    "cellcard": ("08", "08.3.0"),
    "cellcard_wifi": ("08", "08.3.0"),
    "smart": ("08", "08.3.0"),
    "smart_wifi": ("08", "08.3.0"),
    "metfone": ("08", "08.3.0"),
    "realestate": ("04", "04.1.1"),
    "khmer24": ("04", "04.1.1"),
    "edc": ("04", "04.5.1"),
    "ppwsa": ("04", "04.4.1"),
    "redbus": ("07", "07.3.2"),
    "bookmebus": ("07", "07.3.2"),
    "khmermoto": ("07", "07.1.2"),
    "sokhahotel": ("11", "11.2.0"),
    "hyyathotel": ("11", "11.2.0"),
    "bayonbkk": ("11", "11.1.1"),
    "samnangshop": ("08", "08.2.0"),
    "arystore": ("08", "08.2.0"),
}

# 5 Multi-Category Stores requiring Vector Semantic Classification
MULTI_CATEGORY_STORES = {"aeon", "aeon3", "delishop", "l192", "communitypharma", "grab_ucare", "grab_lucky", "grab_chipmong"}

# 12 UN COICOP Official Division Reference Definitions (Bilingual English & Khmer)
COICOP_12_REFERENCE_DEFINITIONS = [
    {
        "division": "01",
        "code": "01.1.1",
        "name": "Food and non-alcoholic beverages",
        "description": "fresh food groceries rice jasmine bread cereals noodles bakery pasta flour fresh meat beef steak pork chicken poultry fresh fish salmon fillet tuna seafood shrimp squid crab fresh milk dairy cheese butter eggs cooking oil vegetable oil palm oil canola oil fresh fruit apples bananas oranges mango fresh vegetables tomatoes potatoes onions chili spices seasoning sugar salt coffee roast ground coffee instant coffee beans tea bags green tea black tea mineral water drinking water bottled spring water 1.5l 500ml fruit juice soft drinks soft drink coca cola coke cola 330ml beverage packaged canned food grocery supermarket ត្រី ត្រីសាម៉ុង ត្រីសាម៉ុងស្រស់ សាច់គោ សាច់ជ្រូក សាច់មាន់ អង្ករ បន្លែ ផ្លែឈើ ទឹកដោះគោ នំប៉័ង មី ប្រេងឆា ស្ករស អំបិល ទឹកត្រី កាហ្វេ តែ ទឹកបរិសុទ្ធ កូកាកូឡា"
    },
    {
        "division": "02",
        "code": "02.1.3",
        "name": "Alcoholic beverages and tobacco",
        "description": "alcohol beer lager stout craft beer angkor beer cambodia beer heineken wine red wine white wine champagne spirits whiskey scotch whisky johnnie walker vodka gin rum tequila cognac liquor tobacco cigarettes cigars rolling tobacco ស្រា ស្រាបៀរ ស្រាបៀរអង្គរ ស្រាក្រហម ស្រាស ស្រាវីស្គី បារី"
    },
    {
        "division": "03",
        "code": "03.1.2",
        "name": "Clothing and footwear",
        "description": "men women clothing apparel fashion shirts t-shirts t shirt crewneck polo pants jeans trousers shorts dresses skirts denim winter jacket coat hoodie sweater underwear socks footwear shoes sneakers leather shoes boots sandals flip-flops slippers athletic footwear children backpack bag ខោអាវ អាវ អាវយឺត ខោ ខោខូវប៊យ រ៉ូប សំពត់ អាវរងា ស្បែកជើង ស្បែកជើងប៉ាតា ស្បែកជើងផ្ទាត់"
    },
    {
        "division": "04",
        "code": "04.1.1",
        "name": "Housing, water, electricity, gas and other fuels",
        "description": "residential home rent apartment rental house lease municipal tap water utility bill piped water supply electricity electric power grid utility bill cooking gas lpg cylinder refill kerosene firewood home maintenance and repair services ផ្ទះ ផ្ទះជួល បន្ទប់ជួល ទឹកស្អាត អគ្គិសនី ហ្គាស"
    },
    {
        "division": "05",
        "code": "05.1.1",
        "name": "Furnishings, household equipment and routine household maintenance",
        "description": "furniture beds sofas tables chairs wardrobes mattresses household textiles bedsheets blankets bath towel cotton curtains kitchenware cookware frying pan pots pans plates glassware cutlery laundry detergent attack liquid dishwashing floor cleaner disinfectants mops brooms trash bags lightbulb led 9w lighting bulb appliance non-stick pan induction តុ កៅអី គ្រែ ពូក ភួយ កន្សែង កម្រាលពូក សាប៊ូបោកខោអាវ ទឹកលាងចាន ទឹកជូតឥដ្ឋ អំពូលភ្លើង"
    },
    {
        "division": "06",
        "code": "06.1.1",
        "name": "Health",
        "description": "pharmaceutical products medicines prescription drugs paracetamol painkillers panadol extra antibiotics cough syrup cold medicine medical balms tiger balm eye drops antiseptic bandages thermometers blood pressure monitor omron vitamins vitamin c 1000mg dietary supplements healthcare dental and medical services tablets capsules pills pharma pharmacy ថ្នាំ ថ្នាំពេទ្យ ប៉ារ៉ាសេតាម៉ុល វីតាមីន បង់រុំរបួស ប្រេងកូឡា ម៉ាស់"
    },
    {
        "division": "07",
        "code": "07.2.2",
        "name": "Transport",
        "description": "automotive fuels gasoline petrol super 95 regular gasoline octane diesel fuel engine motor oil vehicle lubricants bus tickets coach fares luxury bus taxi rides intercity passenger transport motorcycle maintenance tire replacement vehicle repair សាំង ប្រេងសាំង ម៉ាស៊ូត ប្រេងម៉ាស៊ូត ឡាន ម៉ូតូ សំបុត្រឡានក្រុង"
    },
    {
        "division": "08",
        "code": "08.2.0",
        "name": "Communication",
        "description": "mobile phones smartphones apple iphone 15 pro max samsung galaxy cellular mobile data plans vip data voice top-up cards sim cards fiber optic home internet wifi subscriptions telecom services ទូរស័ព្ទ ទូរស័ព្ទដៃ ស៊ីមកាត កាតទូរស័ព្ទ អ៊ីនធឺណិត"
    },
    {
        "division": "09",
        "code": "09.1.1",
        "name": "Recreation and culture",
        "description": "laptop computer 15 inch desktop pc television sets audio speakers bluetooth wireless headphones noise cancelling sony wh-1000xm5 earbuds usb cable type-c cables cameras stationery pens notebooks office paper books toys building blocks toy lego building set board games video game consoles sports equipment fitness dumbbell 5kg workout gear pet food and pet care កុំព្យូទ័រ កុំព្យូទ័រយួរដៃ ទូរទស្សន៍ កាស ធុងបាស សៀវភៅ ប៊ិច ប្រដាប់ក្មេងលេង"
    },
    {
        "division": "10",
        "code": "10.1.0",
        "name": "Education",
        "description": "school tuition fees university semester fees private tutoring language courses vocational training educational textbooks and schooling supplies ការអប់រំ សាលារៀន សាកលវិទ្យាល័យ"
    },
    {
        "division": "11",
        "code": "11.1.1",
        "name": "Restaurants and hotels",
        "description": "hotel accommodation overnight room bookings resort suites sokha hotel restaurant dining services cafe bistro dining meal service coffee shop latte espresso cappuccino catering food court dine-in buffet table service takeaway restaurant order សណ្ឋាគារ អាហារដ្ឋាន ហាងកាហ្វេ"
    },
    {
        "division": "12",
        "code": "12.1.1",
        "name": "Miscellaneous goods and services (Personal Care)",
        "description": "personal hygiene and grooming shampoo hair conditioner head shoulders anti-dandruff hair dye body wash bath soap facial cleansers cleanser cetaphil skincare serum face moisturizers sunscreen spf50 biore uv watery essence lotion toothpaste colgate toothbrushes mouthwash deodorant spray spray deodorants perfumes baby pampers diapers sanitary pads wet wipes razor blades blades pack razors shaving cream cosmetics jewelry suitcases handbags wallets personal care សាប៊ូ សាប៊ូកក់សក់ ក្រែមបន្ទន់សក់ សាប៊ូដុសខ្លួន ថ្នាំដុសធ្មេញ ច្រាសដុសធ្មេញ ឡេការពារកម្តៅថ្ងៃ ឡេលាបខ្លួន ក្រែមលាបមុខ ខោទឹកនោម សំឡីអនាម័យ ទឹកអប់ កាបូប នាឡិកា គ្រឿងអលង្ការ"
    }
]

# Comprehensive 4-Digit / 5-Digit UN COICOP 2018 Reference Taxonomy (Bilingual English & Khmer)
COICOP_4DIGIT_REFERENCE_DEFINITIONS = [
    # ── Division 01: Food & Non-Alcoholic Beverages ─────────────────────────────
    {
        "division": "01",
        "code": "01.1.1",
        "name": "Bread and cereals",
        "description": "rice jasmine rice sticky rice brown rice bread white bread baguette toast noodles instant noodles mama noodles ramen pasta spaghetti macaroni flour wheat flour oats cereals bakery buns pastries croissants អង្ករ អង្ករផ្កាម្លិះ នំប៉័ង មី ម្សៅ ម្សៅមី គ្រាប់ធញ្ញជាតិ"
    },
    {
        "division": "01",
        "code": "01.1.2",
        "name": "Meat",
        "description": "fresh meat beef steak beef slice ground beef pork fresh pork pork belly ribs chicken fresh chicken chicken breast drumstick wings poultry duck sausages hotdog bacon ham meatball jerky សាច់គោ សាច់គោស្រស់ គោ សាច់ជ្រូក សាច់ជ្រូកស្រស់ ជ្រូក សាច់មាន់ សាច់មាន់ស្រស់ មាន់ សាច់ទា សាច់ក្រក"
    },
    {
        "division": "01",
        "code": "01.1.3",
        "name": "Fish and seafood",
        "description": "fresh fish salmon fresh salmon salmon fillet tuna sea bass mackerel catfish shrimp fresh shrimp prawns squid cuttlefish crab lobster dried fish dried shrimp canned fish sardines mackerel fish cake fish ball fermented fish ត្រី ត្រីស្រស់ ត្រីសាម៉ុង ត្រីសាម៉ុងស្រស់ ត្រីធូណា បង្គា មឹក ក្តាម ប្រហុក"
    },
    {
        "division": "01",
        "code": "01.1.4",
        "name": "Milk, cheese and eggs",
        "description": "fresh milk full cream milk skim milk raw milk condensed milk evaporated milk yogurt greek yogurt cheese cheddar mozzarella butter unsalted butter margarine cream eggs chicken eggs duck eggs fresh eggs ទឹកដោះគោ ទឹកដោះគោស្រស់ ទឹកដោះគោឆៅ ឈីស ប៊ឺ យ៉ាអួ ស៊ុត ពងមាន់ ពងទា"
    },
    {
        "division": "01",
        "code": "01.1.5",
        "name": "Oils and fats",
        "description": "cooking oil vegetable oil palm oil canola oil sunflower oil soybean oil olive oil extra virgin olive oil coconut oil sesame oil lard shortening ប្រេងឆា ប្រេងដូង ប្រេងអូលីវ"
    },
    {
        "division": "01",
        "code": "01.1.6",
        "name": "Fruit",
        "description": "fresh fruit apples fuji apple bananas cavendish orange navel orange mandarin mango fresh mango watermelon grapes strawberries dragon fruit papaya pineapple guava durian dried fruit ផ្លែឈើ ផ្លែប៉ោម ផ្លែចេក ចេក ផ្លែក្រូច ក្រូច ផ្លែស្វាយ ស្វាយ ឪឡឹក ទំពាំងបាយជូរ"
    },
    {
        "division": "01",
        "code": "01.1.7",
        "name": "Vegetables",
        "description": "fresh vegetables tomatoes potatoes onions red onion garlic chili green chili ginger carrots cabbage lettuce broccoli spinach cucumber morning glory mushrooms corn herbs spices fresh salad បន្លែ ប៉េងប៉ោះ ដំឡូងបារាំង ខ្ទឹមបារាំង ខ្ទឹមស ម្ទេស ការ៉ុត"
    },
    {
        "division": "01",
        "code": "01.1.8",
        "name": "Sugar, jam, honey, chocolate and confectionery",
        "description": "white sugar brown sugar refined sugar palm sugar honey natural honey strawberry jam fruit preserves chocolate milk chocolate dark chocolate candy gummy sweets lollipop marshmallows cookies biscuits wafers cakes pastries ស្ករស ស្ករត្នោត ទឹកឃ្មុំ សូកូឡា ស្ករគ្រាប់ នំ នំស្រួយ"
    },
    {
        "division": "01",
        "code": "01.1.9",
        "name": "Food products n.e.c.",
        "description": "table salt iodized salt fish sauce soy sauce oyster sauce chili sauce tomato ketchup mayonnaise vinegar black pepper seasoning powder msg chicken powder soup base spices curry paste bouillon cubes អំបិល ទឹកត្រី ទឹកស៊ីអ៊ីវ គ្រឿងទេស"
    },
    {
        "division": "01",
        "code": "01.2.1",
        "name": "Coffee, tea and cocoa",
        "description": "coffee roast ground coffee coffee beans instant coffee nescafe espresso coffee powder drip coffee tea green tea black tea jasmine tea oolong tea tea bags cocoa hot chocolate powder matcha powder កាហ្វេ តែ កាកាវ"
    },
    {
        "division": "01",
        "code": "01.2.2",
        "name": "Mineral waters, soft drinks, fruit and vegetable juices",
        "description": "mineral water drinking water pure water spring water bottled water 500ml 1.5l soft drinks soda carbonated drink coca cola coke pepsi sprite 7up fanta tonic water sparkling water fruit juice orange juice apple juice energy drink red bull sting iced tea ទឹក ទឹកបរិសុទ្ធ ទឹកក្រូច កូកាកូឡា ទឹកផ្លែឈើ"
    },

    # ── Division 02: Alcoholic Beverages & Tobacco ──────────────────────────────
    {
        "division": "02",
        "code": "02.1.1",
        "name": "Spirits and liqueurs",
        "description": "whiskey whisky scotch bourbon johnnie walker chivas regal vodka absolut gin tanqueray rum bacardi tequila cognac hennessy martell brandy soju sake baijiu liqueur ស្រា ស្រាវីស្គី"
    },
    {
        "division": "02",
        "code": "02.1.2",
        "name": "Wine",
        "description": "red wine white wine cabernet sauvignon merlot chardonnay sauvignon blanc rose sparkling wine champagne prosecco ស្រាក្រហម ស្រាស"
    },
    {
        "division": "02",
        "code": "02.1.3",
        "name": "Beer",
        "description": "beer lager stout pilsner ale craft beer angkor beer cambodia beer heineken tiger beer carlsberg singha hoegaarden budweiser draft beer can bottle 330ml 500ml ស្រាបៀរ ស្រាបៀរអង្គរ"
    },
    {
        "division": "02",
        "code": "02.2.0",
        "name": "Tobacco",
        "description": "cigarettes cigars rolling tobacco tobacco leaves menthol cigarettes lighter matches smoking accessories បារី"
    },

    # ── Division 03: Clothing and Footwear ───────────────────────────────────────
    {
        "division": "03",
        "code": "03.1.2",
        "name": "Garments / Clothing",
        "description": "men women children apparel fashion shirts t-shirts polo shirt crewneck button down pants jeans trousers shorts denim dresses evening gown skirts jacket winter coat hoodie sweater underwear bra panties boxer briefs socks swimwear uniform raincoat children backpack bag school bag ខោអាវ អាវ អាវយឺត ខោ ខោខូវប៊យ រ៉ូប សំពត់ អាវរងា"
    },
    {
        "division": "03",
        "code": "03.2.1",
        "name": "Shoes and other footwear",
        "description": "shoes sneakers running shoes athletic shoes leather shoes dress shoes boots sandals flip-flops slippers high heels loafers crocs athletic footwear ស្បែកជើង ស្បែកជើងប៉ាតា ស្បែកជើងផ្ទាត់"
    },

    # ── Division 04: Housing, Water, Electricity, Gas & Other Fuels ─────────────
    {
        "division": "04",
        "code": "04.1.1",
        "name": "Actual rentals for housing",
        "description": "residential house rental apartment rent condo rent room rental lease tenant monthly accommodation lease ផ្ទះ ផ្ទះជួល បន្ទប់ជួល"
    },
    {
        "division": "04",
        "code": "04.4.1",
        "name": "Water supply",
        "description": "municipal tap water clean water supply water utility bill piped water meter tariff ទឹកស្អាត"
    },
    {
        "division": "04",
        "code": "04.5.1",
        "name": "Electricity",
        "description": "electricity bill electric power electric grid utility rate kwh meter edc electric tariff power supply អគ្គិសនី"
    },
    {
        "division": "04",
        "code": "04.5.2",
        "name": "Gas",
        "description": "cooking gas lpg gas cylinder gas tank refill liquefied petroleum gas propane butane gas stove refill ហ្គាស"
    },

    # ── Division 05: Furnishings, Household Equipment & Routine Maintenance ────
    {
        "division": "05",
        "code": "05.1.1",
        "name": "Furniture and furnishings",
        "description": "furniture sofa couch chair dining table office desk bed frame mattress wardrobe closet shelf bookcase cabinet តុ កៅអី គ្រែ ពូក"
    },
    {
        "division": "05",
        "code": "05.2.1",
        "name": "Household textiles",
        "description": "bedsheets bed cover pillow pillowcase blanket quilt duvet bath towel face towel cotton curtains tablecloth ភួយ កន្សែង កម្រាលពូក"
    },
    {
        "division": "05",
        "code": "05.6.1",
        "name": "Non-durable household goods and cleaning products",
        "description": "laundry detergent washing powder liquid detergent fabric softener dishwashing liquid dish soap floor cleaner surface cleaner bleach disinfectant wipes mops brooms trash bags sponge scourer toilet paper tissue paper paper towels lightbulb led bulb insect spray pest control សាប៊ូបោកខោអាវ ទឹកលាងចាន ទឹកជូតឥដ្ឋ អំពូលភ្លើង"
    },

    # ── Division 06: Health ─────────────────────────────────────────────────────
    {
        "division": "06",
        "code": "06.1.1",
        "name": "Pharmaceutical products",
        "description": "pharmaceuticals medicines prescription drugs OTC paracetamol panadol ibuprofen aspirin antibiotics cough syrup cold flu medicine throat lozenges allergy medicine antihistamine antacids vitamins vitamin c multivitamins dietary supplements calcium iron tablets capsules pills eye drops ear drops ថ្នាំ ថ្នាំពេទ្យ ប៉ារ៉ាសេតាម៉ុល វីតាមីន"
    },
    {
        "division": "06",
        "code": "06.1.2",
        "name": "Other medical products and appliances",
        "description": "medical bandages gauze adhesive tape antiseptic betadine tiger balm medicated balm plaster thermometer digital thermometer blood pressure monitor omron face masks surgical mask medical gloves rapid test kit covid test crutches wheelchair first aid kit បង់រុំរបួស ប្រេងកូឡា ម៉ាស់"
    },

    # ── Division 07: Transport ──────────────────────────────────────────────────
    {
        "division": "07",
        "code": "07.2.2",
        "name": "Fuels and lubricants for personal transport equipment",
        "description": "automotive fuel gasoline petrol super 95 regular gasoline octane 92 diesel fuel engine oil motor oil synthetic oil brake fluid transmission fluid lubricants coolant fuel pump សាំង ប្រេងសាំង ម៉ាស៊ូត ប្រេងម៉ាស៊ូត"
    },
    {
        "division": "07",
        "code": "07.3.2",
        "name": "Passenger transport by bus and coach",
        "description": "bus ticket coach ticket intercity bus express bus passenger van transit ticket public transportation bus fare bookmebus redbus fare សំបុត្រឡានក្រុង"
    },

    # ── Division 08: Communication ──────────────────────────────────────────────
    {
        "division": "08",
        "code": "08.2.0",
        "name": "Telephone and communication equipment",
        "description": "mobile phones smartphones smartphone apple iphone iphone 15 pro max samsung galaxy xiaomi oppo vivo feature phone cellular phone tablet cellular handset wireless telephone ទូរស័ព្ទ ទូរស័ព្ទដៃ"
    },
    {
        "division": "08",
        "code": "08.3.0",
        "name": "Telephone and internet services",
        "description": "sim card top-up card phone scratch card mobile data plan cellular data subscription vip data voice pack fiber internet home wifi broadband subscription telecom bill cellcard smart metfone ស៊ីមកាត កាតទូរស័ព្ទ អ៊ីនធឺណិត"
    },

    # ── Division 09: Recreation and Culture ──────────────────────────────────────
    {
        "division": "09",
        "code": "09.1.1",
        "name": "Equipment for sound and picture",
        "description": "television tv smart tv 4k tv audio speakers bluetooth speaker wireless soundbar headphones noise cancelling earphones earbuds sony wh-1000xm5 airpods digital camera camcorder projector home theater ទូរទស្សន៍ កាស ធុងបាស"
    },
    {
        "division": "09",
        "code": "09.1.3",
        "name": "Information processing equipment",
        "description": "computer laptop notebook pc desktop computer macbook ipad tablet pc monitor computer mouse keyboard external hard drive ssd usb flash drive printer scanner computer accessories កុំព្យូទ័រ កុំព្យូទ័រយួរដៃ"
    },
    {
        "division": "09",
        "code": "09.3.1",
        "name": "Games, toys and hobbies",
        "description": "toys children toys building blocks lego action figures dolls board games puzzles video game console playstation nintendo xbox gaming controller sports equipment soccer ball basketball tennis racket dumbbells fitness gear pet food dog food cat food ប្រដាប់ក្មេងលេង"
    },
    {
        "division": "09",
        "code": "09.5.1",
        "name": "Books and stationery",
        "description": "books fiction non-fiction textbooks notebooks notepad stationery ballpoint pens pens pencils highlighter scissors stapler printer paper office supplies art supplies សៀវភៅ ប៊ិច"
    },

    # ── Division 10: Education ──────────────────────────────────────────────────
    {
        "division": "10",
        "code": "10.1.0",
        "name": "Education services",
        "description": "school tuition fees primary secondary high school private tutoring english language courses university semester fees course tuition vocational training educational certificate fees ការអប់រំ សាលារៀន សាកលវិទ្យាល័យ"
    },

    # ── Division 11: Restaurants and Hotels ──────────────────────────────────────
    {
        "division": "11",
        "code": "11.1.1",
        "name": "Restaurants and cafes",
        "description": "restaurant food service cafe dining establishment coffee shop latte cappuccino espresso dine-in buffet table service dining bill restaurant order delivery catering food court service អាហារដ្ឋាន ហាងកាហ្វេ"
    },
    {
        "division": "11",
        "code": "11.2.0",
        "name": "Accommodation services",
        "description": "hotel room accommodation luxury hotel suite resort room booking overnight stay sokha hotel hyatt hotel bayon bkk guest house motel room lodging reservation សណ្ឋាគារ"
    },

    # ── Division 12: Miscellaneous Goods and Services (Personal Care) ────────────
    {
        "division": "12",
        "code": "12.1.1",
        "name": "Hairdressing and hair care",
        "description": "shampoo anti-dandruff head and shoulders pantene loreal hair conditioner hair treatment hair mask hair dye hair styling gel wax pomade hair dryer salon service សាប៊ូកក់សក់ ក្រែមបន្ទន់សក់"
    },
    {
        "division": "12",
        "code": "12.1.3",
        "name": "Personal care, hygiene and cosmetics",
        "description": "body wash shower gel bath soap facial cleanser face wash cetaphil moisturizer face cream serum sunscreen spf50 biore uv sunblock body lotion hand cream toothpaste colgate sensodyne toothbrush mouthwash dental floss deodorant spray roll-on roll on perfume fragrance cologne baby diapers pampers mamy poko sanitary pads wet wipes cotton pads razor razor blades shaving cream lip balm lipstick makeup mascara powder skincare cosmetics សាប៊ូ សាប៊ូដុសខ្លួន ថ្នាំដុសធ្មេញ ច្រាសដុសធ្មេញ ឡេការពារកម្តៅថ្ងៃ ឡេលាបខ្លួន ក្រែមលាបមុខ ខោទឹកនោម សំឡីអនាម័យ ទឹកអប់"
    },
    {
        "division": "12",
        "code": "12.3.1",
        "name": "Jewellery, clocks and watches",
        "description": "jewelry gold silver necklace bracelet ring earrings wrist watch smart watch clock timepieces គ្រឿងអលង្ការ នាឡិកា"
    },
    {
        "division": "12",
        "code": "12.3.2",
        "name": "Other personal effects",
        "description": "handbag purse wallet luggage suitcase travel bag belt sunglasses umbrella leather accessories personal items កាបូប"
    }
]


def _build_semantic_fallback_vector(text: str) -> np.ndarray:
    """Deterministic, high-fidelity semantic vocabulary vector with Khmer compound awareness."""
    t_lower = text.lower()
    raw_tokens = re.findall(r"\b[a-zA-Z0-9\u1780-\u17ff]+\b", t_lower)
    tokens = set(raw_tokens)

    # Extract Khmer morphemes / dictionary mappings
    if is_khmer_text(text):
        kh_tokens = extract_khmer_tokens(text)
        tokens.update(kh_tokens)

    # Khmer compound expansion from consolidated text_clean module
    for compound in KHMER_COMPOUNDS:
        if compound in t_lower:
            tokens.add(compound)
            if "សាម៉ុង" in compound:
                tokens.add("salmon")
                tokens.add("fish")
            elif "គោ" in compound:
                tokens.add("beef")
                tokens.add("meat")
            elif "ជ្រូក" in compound:
                tokens.add("pork")
                tokens.add("meat")
            elif "មាន់" in compound:
                tokens.add("chicken")
                tokens.add("poultry")
            elif "អង្ករ" in compound:
                tokens.add("rice")
                tokens.add("cereal")
            elif "សាំង" in compound:
                tokens.add("gasoline")
                tokens.add("fuel")
            elif "ស្រាបៀរ" in compound:
                tokens.add("beer")
                tokens.add("alcohol")
            elif "កូឡា" in compound:
                tokens.add("coca cola")
                tokens.add("drink")

    vec = np.zeros(768, dtype=np.float32)

    # 1. Base deterministic hash noise (indices 0..699)
    # BUG FIX: Use hashlib instead of hash() which is randomized per-process
    # since Python 3.3 (PYTHONHASHSEED), breaking reproducibility across runs.
    import hashlib
    for tok in tokens:
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16) % 700
        vec[h] += 1.0

    # 2. Key COICOP 12-Division feature dimensions (indices 700..711)
    for i, ref in enumerate(COICOP_12_REFERENCE_DEFINITIONS):
        ref_tokens = set(ref["description"].split())
        overlap = len(tokens & ref_tokens)
        if overlap > 0:
            vec[700 + i] += float(overlap) * 10.0

    # 3. Granular 4-Digit COICOP feature dimensions (indices 712..760)
    for j, ref4 in enumerate(COICOP_4DIGIT_REFERENCE_DEFINITIONS):
        if 712 + j < 768:
            ref4_tokens = set(ref4["description"].split())
            overlap4 = len(tokens & ref4_tokens)
            if overlap4 > 0:
                vec[712 + j] += float(overlap4) * 12.0

    # 4. Contextual Disambiguation Boosts
    # Disambiguate retail grocery coffee/tea (Division 01 / 01.2.1) vs. restaurant/cafe service (Division 11 / 11.1.1)
    is_dining = any(k in tokens for k in ["shop", "cafe", "restaurant", "dining", "hotel", "combo", "latte", "cappuccino", "buffet", "court"])
    is_retail_coffee = any(k in tokens for k in ["coffee", "tea", "beans", "roast", "nescafe", "កាហ្វេ", "តែ"]) and not is_dining
    if is_retail_coffee:
        vec[700] += 25.0  # Division 01
        vec[721] += 30.0  # 01.2.1 Coffee, tea and cocoa

    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


class HybridCOICOPClassifier:
    """12-Division & 4-Digit Multilingual Vector Classifier with Gemini Pro LLM fallback."""

    def __init__(self) -> None:
        self.key_pool = get_key_pool()
        self._local_model = None
        self._embed_cache: dict[str, np.ndarray] = {}
        self._ref_embeddings: list[dict[str, Any]] = []
        self._ref_embeddings_4digit: list[dict[str, Any]] = []
        self._precompute_reference_vectors()

    def _get_local_model(self):
        if self._local_model is None and HAS_SENTENCE_TRANSFORMERS:
            try:
                self._local_model = SentenceTransformer(LOCAL_FALLBACK_MODEL)
            except Exception as e:
                log.warning("Could not load local sentence-transformers model: %s", e)
        return self._local_model

    def embed_text(self, text: str) -> np.ndarray:
        """Generates dense semantic embedding vector via local fallback or Gemini."""
        if not text or not text.strip():
            return np.zeros(768, dtype=np.float32)

        cleaned_text = text.strip()
        if cleaned_text in self._embed_cache:
            return self._embed_cache[cleaned_text]

        use_local_first = os.getenv("USE_LOCAL_FALLBACK_FIRST", "true").lower() in ("true", "1", "yes")
        if not use_local_first and HAS_GENAI and self.key_pool.get_key_count() > 0:
            def _call_gemini(key: str) -> np.ndarray:
                genai.configure(api_key=key)
                res = genai.embed_content(model=EMBEDDING_MODEL, content=cleaned_text)
                return np.array(res["embedding"], dtype=np.float32)

            try:
                vec = self.key_pool.execute_with_retry(_call_gemini)
                self._embed_cache[cleaned_text] = vec
                return vec
            except Exception as exc:
                log.warning("Gemini embedding API failed; falling back to local: %s", exc)

        local_model = self._get_local_model()
        if local_model is not None:
            vec = local_model.encode(cleaned_text)
            local_vec = np.array(vec, dtype=np.float32)
            if local_vec.shape[0] < 768:
                padded = np.zeros(768, dtype=np.float32)
                padded[: local_vec.shape[0]] = local_vec
                self._embed_cache[cleaned_text] = padded
                return padded
            result_vec = local_vec[:768]
            self._embed_cache[cleaned_text] = result_vec
            return result_vec

        res_vec = _build_semantic_fallback_vector(cleaned_text)
        self._embed_cache[cleaned_text] = res_vec
        return res_vec

    def embed_batch(self, texts: list[str], batch_size: int = 50) -> list[np.ndarray]:
        """Generates dense semantic embedding vectors in batches via Gemini or local model."""
        if not texts:
            return []

        results: list[np.ndarray | None] = [None] * len(texts)
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        for idx, t in enumerate(texts):
            clean = (t or "").strip()
            if not clean:
                results[idx] = np.zeros(768, dtype=np.float32)
            elif clean in self._embed_cache:
                results[idx] = self._embed_cache[clean]
            else:
                uncached_indices.append(idx)
                uncached_texts.append(clean)

        if not uncached_texts:
            return [r if r is not None else np.zeros(768, dtype=np.float32) for r in results]

        use_local_first = os.getenv("USE_LOCAL_FALLBACK_FIRST", "true").lower() in ("true", "1", "yes")
        if not use_local_first and HAS_GENAI and self.key_pool.get_key_count() > 0:
            for b_start in range(0, len(uncached_texts), batch_size):
                b_texts = uncached_texts[b_start : b_start + batch_size]
                b_indices = uncached_indices[b_start : b_start + batch_size]

                def _call_gemini_batch_embed(key: str, batch_items: list[str] = b_texts) -> list[np.ndarray]:
                    genai.configure(api_key=key)
                    res = genai.embed_content(model=EMBEDDING_MODEL, content=batch_items)
                    embeddings = res.get("embedding", [])
                    return [np.array(e, dtype=np.float32) for e in embeddings]

                try:
                    b_vecs = self.key_pool.execute_with_retry(_call_gemini_batch_embed)
                    for orig_idx, vec in zip(b_indices, b_vecs):
                        clean_str = texts[orig_idx].strip()
                        self._embed_cache[clean_str] = vec
                        results[orig_idx] = vec
                except Exception as exc:
                    log.warning("Gemini batch embedding API failed; falling back to local/individual: %s", exc)
                    for orig_idx in b_indices:
                        results[orig_idx] = self.embed_text(texts[orig_idx])
        else:
            local_model = self._get_local_model()
            if local_model is not None:
                try:
                    vecs = local_model.encode(uncached_texts, batch_size=batch_size)
                    for orig_idx, clean_str, vec in zip(uncached_indices, uncached_texts, vecs):
                        local_vec = np.array(vec, dtype=np.float32)
                        if local_vec.shape[0] < 768:
                            padded = np.zeros(768, dtype=np.float32)
                            padded[: local_vec.shape[0]] = local_vec
                            res_v = padded
                        else:
                            res_v = local_vec[:768]
                        self._embed_cache[clean_str] = res_v
                        results[orig_idx] = res_v
                except Exception as e:
                    log.warning("Local batch encoding failed: %s; falling back to individual", e)
                    for orig_idx in uncached_indices:
                        results[orig_idx] = self.embed_text(texts[orig_idx])
            else:
                for orig_idx in uncached_indices:
                    results[orig_idx] = self.embed_text(texts[orig_idx])

        return [r if r is not None else np.zeros(768, dtype=np.float32) for r in results]

    def _precompute_reference_vectors(self) -> None:
        """Embeds the 12 official UN COICOP divisions and granular 4-digit reference definitions."""
        # 1. 12 Primary Divisions
        div_texts = [ref["description"] for ref in COICOP_12_REFERENCE_DEFINITIONS]
        div_vectors = self.embed_batch(div_texts)
        self._ref_embeddings = [
            {
                "division": ref["division"],
                "code": ref["code"],
                "name": ref["name"],
                "vector": vec,
            }
            for ref, vec in zip(COICOP_12_REFERENCE_DEFINITIONS, div_vectors)
        ]

        # 2. Granular 4-Digit Classes
        d4_texts = [ref4["description"] for ref4 in COICOP_4DIGIT_REFERENCE_DEFINITIONS]
        d4_vectors = self.embed_batch(d4_texts)
        self._ref_embeddings_4digit = [
            {
                "division": ref4["division"],
                "code": ref4["code"],
                "name": ref4["name"],
                "vector": vec4,
            }
            for ref4, vec4 in zip(COICOP_4DIGIT_REFERENCE_DEFINITIONS, d4_vectors)
        ]

    def classify_product(
        self,
        product_name: str,
        store_slug: str = "",
        threshold: float = 0.40,
    ) -> dict[str, Any]:
        """Classifies a product into UN COICOP using Domain Purity -> Vector Cosine -> LLM Fallback."""
        clean_name = product_name.strip()

        # Tier 2: Check Single-Category Pure Store Purity
        if store_slug and store_slug.lower() in PURE_STORE_MAP:
            if store_slug.lower() == "new_gasoline" and "lpg" in clean_name.lower():
                div, code = ("04", "04.5.2")
            else:
                div, code = PURE_STORE_MAP[store_slug.lower()]
            return {
                "product_name": clean_name,
                "coicop_division": div,
                "coicop_code": code,
                "coicop_class_name": self._get_class_name(code, div),
                "confidence_score": 1.0,
                "classification_method": "store_purity",
                "reasoning": f"Store '{store_slug}' is a single-category pure domain ({div}).",
            }

        # Tier 3: Vector Cosine against 4-Digit and 12-Division Reference Categories
        prod_vec = self.embed_text(clean_name)
        prod_norm = np.linalg.norm(prod_vec)
        if prod_norm == 0:
            prod_norm = 1.0

        # Match across 4-Digit Granular Classes if present
        best_4digit = None
        highest_sim_4digit = -1.0
        for ref4 in self._ref_embeddings_4digit:
            ref_vec = ref4["vector"]
            ref_norm = np.linalg.norm(ref_vec)
            if ref_norm == 0:
                ref_norm = 1.0
            sim = float(np.dot(prod_vec, ref_vec) / (prod_norm * ref_norm))
            if sim > highest_sim_4digit:
                highest_sim_4digit = sim
                best_4digit = ref4

        # Match across 12-Division Spaces
        best_div = None
        highest_sim_div = -1.0
        for ref in self._ref_embeddings:
            ref_vec = ref["vector"]
            ref_norm = np.linalg.norm(ref_vec)
            if ref_norm == 0:
                ref_norm = 1.0
            sim = float(np.dot(prod_vec, ref_vec) / (prod_norm * ref_norm))
            if sim > highest_sim_div:
                highest_sim_div = sim
                best_div = ref

        use_local_first = os.getenv("USE_LOCAL_FALLBACK_FIRST", "true").lower() in ("true", "1", "yes")

        # Prefer high-resolution 4-digit match if score is competitive
        if best_4digit and best_div:
            if highest_sim_4digit >= highest_sim_div - 0.05:
                winning_match = best_4digit
                winning_sim = highest_sim_4digit
            else:
                winning_match = best_div
                winning_sim = highest_sim_div
        elif best_4digit:
            winning_match = best_4digit
            winning_sim = highest_sim_4digit
        else:
            winning_match = best_div
            winning_sim = highest_sim_div

        if winning_match and (winning_sim >= threshold or use_local_first):
            final_div = winning_match["division"]
            final_code = winning_match["code"]
            final_name = winning_match["name"]
            
            # Store Context Override: Retail grocers do not sell hotel services (11.2) or municipal utilities (04.1/04.4).
            if store_slug and store_slug.lower() in MULTI_CATEGORY_STORES:
                if final_div == "11":
                    name_low = clean_name.lower()
                    if any(w in name_low for w in ["chicken", "pork", "beef", "meat", "duck", "sausage"]):
                        final_div, final_code, final_name = "01", "01.1.2", "Meat"
                    elif any(w in name_low for w in ["fish", "salmon", "tuna", "seafood", "shrimp"]):
                        final_div, final_code, final_name = "01", "01.1.3", "Fish and seafood"
                    elif any(w in name_low for w in ["bread", "bakery", "croissant", "baguette", "noodle", "pasta"]):
                        final_div, final_code, final_name = "01", "01.1.1", "Bread and cereals"
                    elif any(w in name_low for w in ["coffee", "tea", "cacao", "cocoa"]):
                        final_div, final_code, final_name = "01", "01.2.1", "Coffee, tea and cocoa"
                    elif any(w in name_low for w in ["juice", "water", "soda", "drink"]):
                        final_div, final_code, final_name = "01", "01.2.2", "Mineral waters, soft drinks, fruit and vegetable juices"
                    else:
                        final_div, final_code, final_name = "01", "01.1.9", "Food products n.e.c."
                elif final_div == "04" and final_code in ("04.1.1", "04.4.1"):
                    # Disqualify supermarket items from rentals or municipal tap water
                    name_low = clean_name.lower()
                    if "water gun" in name_low:
                        final_div, final_code, final_name = "09", "09.3.1", "Games, toys and hobbies"
                    elif "water color" in name_low or "pencils" in name_low:
                        final_div, final_code, final_name = "09", "09.5.4", "Stationery and drawing materials"
                    elif any(w in name_low for w in ["water", "juice", "drink"]):
                        final_div, final_code, final_name = "01", "01.2.2", "Mineral waters, soft drinks, fruit and vegetable juices"
                    else:
                        final_div, final_code, final_name = "01", "01.1.9", "Food products n.e.c."

            return {
                "product_name": clean_name,
                "coicop_division": final_div,
                "coicop_code": final_code,
                "coicop_class_name": final_name,
                "confidence_score": round(max(winning_sim, 0.50), 4),
                "classification_method": "vector_embedding",
                "reasoning": f"Matched vector semantics for {winning_match['name']} ({winning_sim:.3f}).",
            }

        # Tier 4: Gemini Pro/Flash LLM Fallback for ambiguous edge cases (< threshold when not in local-first mode)
        if not use_local_first:
            return self.classify_with_llm(clean_name, store_slug)

        return {
            "product_name": clean_name,
            "coicop_division": "01",
            "coicop_code": "01.1.1",
            "coicop_class_name": "Bread and cereals",
            "confidence_score": 0.50,
            "classification_method": "fallback_default",
            "reasoning": "Local fallback default assigned.",
        }

    def classify_product_4digit(
        self,
        product_name: str,
        store_slug: str = "",
        threshold: float = 0.40,
    ) -> dict[str, Any]:
        """Explicit entry point for 4-digit / 5-digit COICOP class resolution."""
        return self.classify_product(product_name, store_slug=store_slug, threshold=threshold)

    def _get_class_name(self, code: str, division: str) -> str:
        """Looks up human-readable class name from code."""
        for r4 in COICOP_4DIGIT_REFERENCE_DEFINITIONS:
            if r4["code"] == code:
                return r4["name"]
        for r12 in COICOP_12_REFERENCE_DEFINITIONS:
            if r12["division"] == division:
                return r12["name"]
        return "Unclassified"

    def classify_with_llm(self, product_name: str, store_slug: str = "") -> dict[str, Any]:
        """Calls Gemini Pro/Flash for deep contextual economic classification."""
        if not HAS_GENAI or self.key_pool.get_key_count() == 0:
            return {
                "product_name": product_name,
                "coicop_division": "01",
                "coicop_code": "01.1.1",
                "coicop_class_name": "Bread and cereals",
                "confidence_score": 0.50,
                "classification_method": "fallback_default",
                "reasoning": "No API keys configured; fallback assigned.",
            }

        prompt = f"""You are an expert statistical classifier for UN COICOP 2018.
Classify this Cambodian retail product into its exact 2-digit division (e.g. '01', '06', '12') and 5-digit COICOP code (e.g. '01.1.1', '01.1.3', '06.1.1', '12.1.3').

Product: "{product_name}"
Retailer context: "{store_slug}"

Rules:
- Packaged food/groceries sold in supermarkets (even if named after dishes) are Division 01.
  - Rice, bread, noodles, flour -> 01.1.1
  - Fresh/frozen meat (beef, pork, chicken) -> 01.1.2
  - Fresh/frozen fish, salmon, shrimp, seafood -> 01.1.3
  - Milk, cheese, eggs, butter, yogurt -> 01.1.4
  - Cooking oil, olive oil -> 01.1.5
  - Fresh fruit (apples, bananas, oranges, mango) -> 01.1.6
  - Fresh vegetables (tomatoes, potatoes, onions, chili) -> 01.1.7
  - Sugar, honey, chocolate, candy, biscuits -> 01.1.8
  - Salt, fish sauce, soy sauce, spices -> 01.1.9
  - Coffee, tea, cocoa -> 01.2.1
  - Bottled water, soft drinks, juices, sodas -> 01.2.2
- Medicines, painkillers, and medical balms are Division 06 (06.1.1 or 06.1.2).
- Hair care, skincare, shampoos, sunscreen, soaps, and cosmetics are Division 12 (12.1.1 or 12.1.3).
- Beer, wine, and spirits are Division 02 (02.1.1 spirits, 02.1.2 wine, 02.1.3 beer).

Return strict JSON only:
{{
  "coicop_division": "01",
  "coicop_code": "01.1.3",
  "confidence_score": 0.95,
  "reasoning": "short explanation under 10 words"
}}"""

        def _call_gemini_llm(key: str) -> dict[str, Any]:
            genai.configure(api_key=key)
            model = genai.GenerativeModel(LLM_MODEL)
            resp = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"},
            )
            data = json.loads(resp.text)
            div = str(data.get("coicop_division", "01")).zfill(2)
            code = str(data.get("coicop_code", "01.1.1"))
            return {
                "product_name": product_name,
                "coicop_division": div,
                "coicop_code": code,
                "coicop_class_name": self._get_class_name(code, div),
                "confidence_score": float(data.get("confidence_score", 0.90)),
                "classification_method": "gemini_llm",
                "reasoning": str(data.get("reasoning", "Gemini AI classification")),
            }

        try:
            return self.key_pool.execute_with_retry(_call_gemini_llm)
        except Exception as e:
            log.warning("Gemini AI classification failed for '%s': %s", product_name, e)
            return {
                "product_name": product_name,
                "coicop_division": "99",
                "coicop_code": "99.9.9",
                "coicop_class_name": "Unclassified",
                "confidence_score": 0.0,
                "classification_method": "llm_error",
                "reasoning": f"LLM error: {e}",
            }

    def classify_batch_with_llm(
        self,
        items: list[dict[str, str]],
        batch_size: int = 40,
    ) -> list[dict[str, Any]]:
        """Batched Gemini classification for multiple ambiguous products in a single API call."""
        if not items:
            return []
        if not HAS_GENAI or self.key_pool.get_key_count() == 0:
            return [
                {
                    "product_name": it.get("product_name", ""),
                    "coicop_division": "01",
                    "coicop_code": "01.1.1",
                    "coicop_class_name": "Bread and cereals",
                    "confidence_score": 0.50,
                    "classification_method": "fallback_default",
                    "reasoning": "No API keys configured; fallback assigned.",
                }
                for it in items
            ]

        results = []
        for i in range(0, len(items), batch_size):
            chunk = items[i : i + batch_size]
            prompt_items = [
                {"name": it.get("product_name", ""), "store": it.get("store_slug", "")}
                for it in chunk
            ]
            prompt = (
                "You are an expert UN COICOP 2018 statistical classifier. "
                "Classify each product in the JSON array below into its 2-digit division ('01'-'12') "
                "and dotted 5-digit COICOP code (e.g. '01.1.1', '06.1.1', '12.1.3').\n\n"
                f"Products:\n{json.dumps(prompt_items, ensure_ascii=False)}\n\n"
                "Return a strict JSON array of objects:\n"
                '[{"product_name": "...", "coicop_division": "01", "coicop_code": "01.1.1", "confidence_score": 0.95, "reasoning": "..."}]'
            )

            def _call_gemini_batch(key: str, batch_prompt: str = prompt) -> list[dict[str, Any]]:
                genai.configure(api_key=key)
                model = genai.GenerativeModel(LLM_MODEL)
                resp = model.generate_content(
                    batch_prompt,
                    generation_config={"response_mime_type": "application/json"},
                )
                text_clean = resp.text.strip()
                if text_clean.startswith("```"):
                    text_clean = re.sub(r"^```(?:json)?\s*", "", text_clean)
                    text_clean = re.sub(r"\s*```$", "", text_clean)
                parsed = json.loads(text_clean)
                chunk_results = []
                for p in parsed:
                    div = str(p.get("coicop_division", "01")).zfill(2)
                    code = str(p.get("coicop_code", "01.1.1"))
                    chunk_results.append({
                        "product_name": p.get("product_name", ""),
                        "coicop_division": div,
                        "coicop_code": code,
                        "coicop_class_name": self._get_class_name(code, div),
                        "confidence_score": float(p.get("confidence_score", 0.90)),
                        "classification_method": "gemini_llm_batch",
                        "reasoning": str(p.get("reasoning", "Gemini AI batch classification")),
                    })
                return chunk_results

            try:
                batch_res = self.key_pool.execute_with_retry(_call_gemini_batch)
                results.extend(batch_res)
            except Exception as e:
                log.warning("Batch LLM classification failed for chunk of %d items: %s. Falling back to individual defaults.", len(chunk), e)
                for it in chunk:
                    results.append({
                        "product_name": it.get("product_name", ""),
                        "coicop_division": "99",
                        "coicop_code": "99.9.9",
                        "coicop_class_name": "Unclassified",
                        "confidence_score": 0.0,
                        "classification_method": "llm_error",
                        "reasoning": f"LLM batch error: {e}",
                    })
        return results


_global_classifier: HybridCOICOPClassifier | None = None


def get_hybrid_classifier() -> HybridCOICOPClassifier:
    """Returns or initializes the global HybridCOICOPClassifier singleton."""
    global _global_classifier
    if _global_classifier is None:
        _global_classifier = HybridCOICOPClassifier()
    return _global_classifier

