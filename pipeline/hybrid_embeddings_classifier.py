"""
pipeline/hybrid_embeddings_classifier.py
────────────────────────────────────────
Hybrid Multilingual Vector Embeddings + Hierarchical Local-First AI COICOP Classifier.
(Local-First Intelligence Architecture).

Classification Flow:
1. Tier 1: Store Purity (Deterministic)
2. Tier 2: Vector Cosine (Semantic Reference Space)
3. Tier 3: Hierarchical AI (Ollama local -> Gemini Cloud)
    a. Ollama Classifier proposes code + reason.
    b. Ollama Judge audits against rules.
    c. If conflict/low-conf -> Gemini Pro resolves.
    d. If still unresolved -> Flag for Human Review.
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
from pipeline.ollama_client import OllamaClient

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
    except ImportError:
        genai = None
        HAS_GENAI = False

try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    SentenceTransformer = None
    HAS_SENTENCE_TRANSFORMERS = False

log = logging.getLogger(__name__)

EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-2")
LLM_MODEL = os.getenv("GEMINI_PRO_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))
LOCAL_FALLBACK_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# Single-Category Pure Stores
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

MULTI_CATEGORY_STORES = {"aeon", "aeon3", "delishop", "l192", "communitypharma", "grab_ucare", "grab_lucky", "grab_chipmong"}

COICOP_12_REFERENCE_DEFINITIONS = [
    {"division": "01", "code": "01.1.1", "name": "Food and non-alcoholic beverages", "description": "fresh food groceries rice jasmine bread cereals noodles bakery pasta flour fresh meat beef steak pork chicken poultry fresh fish salmon fillet tuna seafood shrimp squid crab fresh milk dairy cheese butter eggs cooking oil vegetable oil palm oil canola oil fresh fruit apples bananas oranges mango fresh vegetables tomatoes potatoes onions chili spices seasoning sugar salt coffee roast ground coffee instant coffee beans tea bags green tea black tea mineral water drinking water bottled spring water 1.5l 500ml fruit juice soft drinks soft drink coca cola coke cola 330ml beverage packaged canned food grocery supermarket ត្រី ត្រីសាម៉ុង ត្រីសាម៉ុងស្រស់ សាច់គោ សាច់ជ្រូក សាច់មាន់ អង្ករ បន្លែ ផ្លែឈើ ទឹកដោះគោ នំប៉័ង មី ប្រេងឆា ស្ករស អំបិល ទឹកត្រី កាហ្វេ តែ ទឹកបរិសុទ្ធ កូកាកូឡា"},
    {"division": "02", "code": "02.1.3", "name": "Alcoholic beverages and tobacco", "description": "alcohol beer lager stout craft beer angkor beer cambodia beer heineken wine red wine white wine champagne spirits whiskey scotch whisky johnnie walker vodka gin rum tequila cognac liquor tobacco cigarettes cigars rolling tobacco ស្រា ស្រាបៀរ ស្រាបៀរអង្គរ ស្រាក្រហម ស្រាស ស្រាវីស្គី បារី"},
    {"division": "03", "code": "03.1.2", "name": "Clothing and footwear", "description": "men women clothing apparel fashion shirts t-shirts t shirt crewneck polo pants jeans trousers shorts dresses skirts denim winter jacket coat hoodie sweater underwear socks footwear shoes sneakers leather shoes boots sandals flip-flops slippers athletic footwear children backpack bag ខោអាវ អាវ អាវយឺត ខោ ខោខូវប៊យ រ៉ូប សំពត់ អាវរងា ស្បែកជើង ស្បែកជើងប៉ាតា ស្បែកជើងផ្ទាត់"},
    {"division": "04", "code": "04.1.1", "name": "Housing, water, electricity, gas and other fuels", "description": "residential home rent apartment rental house lease municipal tap water utility bill piped water supply electricity electric power grid utility bill cooking gas lpg cylinder refill kerosene firewood home maintenance and repair services ផ្ទះ ផ្ទះជួល បន្ទប់ជួល ទឹកស្អាត អគ្គិសនី ហ្គាស"},
    {"division": "05", "code": "05.1.1", "name": "Furnishings, household equipment and routine household maintenance", "description": "furniture beds sofas tables chairs wardrobes mattresses household textiles bedsheets blankets bath towel cotton curtains kitchenware cookware frying pan pots pans plates glassware cutlery laundry detergent attack liquid dishwashing floor cleaner disinfectants mops brooms trash bags lightbulb led 9w lighting bulb appliance non-stick pan induction តុ កៅអី គ្រែ ពូក ភួយ កន្សែង កម្រាលពូក សាប៊ូបោកខោអាវ ទឹកលាងចាន ទឹកជូតឥដ្ឋ អំពូលភ្លើង"},
    {"division": "06", "code": "06.1.1", "name": "Health", "description": "pharmaceutical products medicines prescription drugs paracetamol painkillers panadol extra antibiotics cough syrup cold medicine medical balms tiger balm eye drops antiseptic bandages thermometers blood pressure monitor omron vitamins vitamin c 1000mg dietary supplements healthcare dental and medical services tablets capsules pills pharma pharmacy ថ្នាំ ថ្នាំពេទ្យ ប៉ារ៉ាសេតាម៉ុល វីតាមីន បង់រុំរបួស ប្រេងកូឡា ម៉ាស់"},
    {"division": "07", "code": "07.2.2", "name": "Transport", "description": "automotive fuels gasoline petrol super 95 regular gasoline octane diesel fuel engine motor oil vehicle lubricants bus tickets coach fares luxury bus taxi rides intercity passenger transport motorcycle maintenance tire replacement vehicle repair សាំង ប្រេងសាំង ម៉ាស៊ូត ប្រេងម៉ាស៊ូត ឡាន ម៉ូតូ សំបុត្រឡានក្រុង"},
    {"division": "08", "code": "08.2.0", "name": "Communication", "description": "mobile phones smartphones apple iphone 15 pro max samsung galaxy cellular mobile data plans vip data voice top-up cards sim cards fiber optic home internet wifi subscriptions telecom services ទូរស័ព្ទ ទូរស័ព្ទដៃ ស៊ីមកាត កាតទូរស័ព្ទ អ៊ីនធឺណិត"},
    {"division": "09", "code": "09.1.1", "name": "Recreation and culture", "description": "laptop computer 15 inch desktop pc television sets audio speakers bluetooth wireless headphones noise cancelling sony wh-1000xm5 earbuds usb cable type-c cables cameras stationery pens notebooks office paper books toys building blocks toy lego building set board games video game consoles sports equipment fitness dumbbell 5kg workout gear pet food and pet care កុំព្យូទ័រ កុំព្យូទ័រយួរដៃ ទូរទស្សន៍ កាស ធុងបាស សៀវភៅ ប៊ិច ប្រដាប់ក្មេងលេង"},
    {"division": "10", "code": "10.1.0", "name": "Education", "description": "school tuition fees university semester fees private tutoring language courses vocational training educational textbooks and schooling supplies ការអប់រំ សាលារៀន សាកលវិទ្យាល័យ"},
    {"division": "11", "code": "11.1.1", "name": "Restaurants and hotels", "description": "hotel accommodation overnight room bookings resort suites sokha hotel restaurant dining services cafe bistro dining meal service coffee shop latte espresso cappuccino catering food court dine-in buffet table service takeaway restaurant order សណ្ឋាគារ អាហារដ្ឋាន ហាងកាហ្វេ"},
    {"division": "12", "code": "12.1.1", "name": "Miscellaneous goods and services (Personal Care)", "description": "personal hygiene and grooming shampoo hair conditioner head shoulders anti-dandruff hair dye body wash bath soap facial cleansers cleanser cetaphil skincare serum face moisturizers sunscreen spf50 biore uv watery essence lotion toothpaste colgate toothbrushes mouthwash deodorant spray spray deodorants perfumes baby pampers diapers sanitary pads wet wipes razor blades blades pack razors shaving cream cosmetics jewelry suitcases handbags wallets personal care សាប៊ូ សាប៊ូកក់សក់ ក្រែមបន្ទន់សក់ សាប៊ូដុសខ្លួន ថ្នាំដុសធ្មេញ ច្រាសដុសធ្មេញ ឡេការពារកម្តៅថ្ងៃ ឡេលាបខ្លួន ក្រែមលាបមុខ ខោទឹកនោម សំឡីអនាម័យ ទឹកអប់ កាបូប នាឡិកា គ្រឿងអលង្ការ"},
]

COICOP_4DIGIT_REFERENCE_DEFINITIONS = [
    {"division": "01", "code": "01.1.1", "name": "Bread and cereals", "description": "rice jasmine rice sticky rice brown rice bread white bread baguette toast noodles instant noodles mama noodles ramen pasta spaghetti macaroni flour wheat flour oats cereals bakery buns pastries croissants អង្ករ អង្ករផ្កាម្លិះ នំប៉័ង មី ម្សៅ ម្សៅមី គ្រាប់ធញ្ញជាតិ"},
    {"division": "01", "code": "01.1.2", "name": "Meat", "description": "fresh meat beef steak beef slice ground beef pork fresh pork pork belly ribs chicken fresh chicken chicken breast drumstick wings poultry duck sausages hotdog bacon ham meatball jerky សាច់គោ សាច់គោស្រស់ គោ សាច់ជ្រូក សាច់ជ្រូកស្រស់ ជ្រូក សាច់មាន់ សាច់មាន់ស្រស់ មាន់ សាច់ទា សាច់ក្រក"},
    {"division": "01", "code": "01.1.3", "name": "Fish and seafood", "description": "fresh fish salmon fresh salmon salmon fillet tuna sea bass mackerel catfish shrimp fresh shrimp prawns squid cuttlefish crab lobster dried fish dried shrimp canned fish sardines mackerel fish cake fish ball fermented fish ត្រី ត្រីស្រស់ ត្រីសាម៉ុង ត្រីសាម៉ុងស្រស់ ត្រីធូណា បង្គា មឹក ក្តាម ប្រហុក"},
    {"division": "01", "code": "01.1.4", "name": "Milk, cheese and eggs", "description": "fresh milk full cream milk skim milk raw milk condensed milk evaporated milk yogurt greek yogurt cheese cheddar mozzarella butter unsalted butter margarine cream eggs chicken eggs duck eggs fresh eggs ទឹកដោះគោ ទឹកដោះគោស្រស់ ទឹកដោះគោឆៅ ឈីស ប៊ឺ យ៉ាអួ ស៊ុត ពងមាន់ ពងទา"},
    {"division": "01", "code": "01.1.5", "name": "Oils and fats", "description": "cooking oil vegetable oil palm oil canola oil sunflower oil soybean oil olive oil extra virgin olive oil coconut oil sesame oil lard shortening ប្រេងឆา ប្រេងដូង ប្រេងអូលីវ"},
    {"division": "01", "code": "01.1.6", "name": "Fruit", "description": "fresh fruit apples fuji apple bananas cavendish orange navel orange mandarin mango fresh mango watermelon grapes strawberries dragon fruit papaya pineapple guava durian dried fruit ផ្លែឈើ ផ្លែប៉ោម ផ្លែចេក ចេក ផ្លែក្រូច ក្រូច ផ្លែស្វាយ ស្វាយ ឪឡឹក ទំពាំងបាយជូរ"},
    {"division": "01", "code": "01.1.7", "name": "Vegetables", "description": "fresh vegetables tomatoes potatoes onions red onion garlic chili green chili ginger carrots cabbage lettuce broccoli spinach cucumber morning glory mushrooms corn herbs spices fresh salad បន្លែ ប៉េងប៉ោះ ដំឡូងបារាំង ខ្ទឹមបារាំង ខ្ទឹមស ម្ទេស ការ៉ុត"},
    {"division": "01", "code": "01.1.8", "name": "Sugar, jam, honey, chocolate and confectionery", "description": "white sugar brown sugar refined sugar palm sugar honey natural honey strawberry jam fruit preserves chocolate milk chocolate dark chocolate candy gummy sweets lollipop marshmallows cookies biscuits wafers cakes pastries ស្ករស ស្ករត្នោត ទឹកឃ្មុំ សូកូឡា ស្ករគ្រាប់ នំ នំស្រួយ"},
    {"division": "01", "code": "01.1.9", "name": "Food products n.e.c.", "description": "table salt iodized salt fish sauce soy sauce oyster sauce chili sauce tomato ketchup mayonnaise vinegar black pepper seasoning powder msg chicken powder soup base spices curry paste bouillon cubes អំបិល ទឹកត្រី ទឹកស៊ីអ៊ីវ គ្រឿងទេស"},
    {"division": "01", "code": "01.2.1", "name": "Coffee, tea and cocoa", "description": "coffee roast ground coffee coffee beans instant coffee nescafe espresso coffee powder drip coffee tea green tea black tea jasmine tea oolong tea tea bags cocoa hot chocolate powder matcha powder កាហ្វេ តែ កាកាវ"},
    {"division": "01", "code": "01.2.2", "name": "Mineral waters, soft drinks, fruit and vegetable juices", "description": "mineral water drinking water pure water spring water bottled water 500ml 1.5l soft drinks soda carbonated drink coca cola coke pepsi sprite 7up fanta tonic water sparkling water fruit juice orange juice apple juice energy drink red bull sting iced tea ទឹក ទឹកបរិសុទ្ធ ទឹកក្រូច កូកាកូឡា ទឹកផ្លែឈើ"},
    {"division": "02", "code": "02.1.1", "name": "Spirits and liqueurs", "description": "whiskey whisky scotch bourbon johnnie walker chivas regal vodka absolut gin tanqueray rum bacardi tequila cognac hennessy martell brandy soju sake baijiu liqueur ស្រา ស្រាវីស្គី"},
    {"division": "02", "code": "02.1.2", "name": "Wine", "description": "red wine white wine cabernet sauvignon merlot chardonnay sauvignon blanc rose sparkling wine champagne prosecco ស្រាក្រហម ស្រាស"},
    {"division": "02", "code": "02.1.3", "name": "Beer", "description": "beer lager stout pilsner ale craft beer angkor beer cambodia beer heineken tiger beer carlsberg singha hoegaarden budweiser draft beer can bottle 330ml 500ml ស្រាបៀរ ស្រាបៀរអង្គរ"},
    {"division": "02", "code": "02.2.0", "name": "Tobacco", "description": "cigarettes cigars rolling tobacco tobacco leaves menthol cigarettes lighter matches smoking accessories បារី"},
    {"division": "03", "code": "03.1.2", "name": "Garments / Clothing", "description": "men women children apparel fashion shirts t-shirts polo shirt crewneck button down pants jeans trousers shorts denim dresses evening gown skirts jacket winter coat hoodie sweater underwear bra panties boxer briefs socks swimwear uniform raincoat children backpack bag school bag ខោអាវ អាវ អាវយឺត ខោ ខោខូវប៊យ រ៉ូប សំពត់ អាវរងា"},
    {"division": "03", "code": "03.2.1", "name": "Shoes and other footwear", "description": "shoes sneakers running shoes athletic shoes leather shoes dress shoes boots sandals flip-flops slippers high heels loafers crocs athletic footwear ស្បែកជើង ស្បែកជើងប៉ាតា ស្បែកជើងផ្ទាត់"},
    {"division": "04", "code": "04.1.1", "name": "Actual rentals for housing", "description": "residential house rental apartment rent condo rent room rental lease tenant monthly accommodation lease ផ្ទះ ផ្ទះជួល បន្ទប់ជួល"},
    {"division": "04", "code": "04.4.1", "name": "Water supply", "description": "municipal tap water clean water supply water utility bill piped water meter tariff ទឹកស្អាត"},
    {"division": "04", "code": "04.5.1", "name": "Electricity", "description": "electricity bill electric power electric grid utility rate kwh meter edc electric tariff power supply អគ្គិសនី"},
    {"division": "04", "code": "04.5.2", "name": "Gas", "description": "cooking gas lpg gas cylinder gas tank refill liquefied petroleum gas propane butane gas stove refill ហ្គាស"},
    {"division": "05", "code": "05.1.1", "name": "Furniture and furnishings", "description": "furniture sofa couch chair dining table office desk bed frame mattress wardrobe closet shelf bookcase cabinet តុ កៅអី គ្រែ ពូក"},
    {"division": "05", "code": "05.2.1", "name": "Household textiles", "description": "bedsheets bed cover pillow pillowcase blanket quilt duvet bath towel face towel cotton curtains tablecloth ភួយ កន្សែង កម្រាលពូក"},
    {"division": "05", "code": "05.6.1", "name": "Non-durable household goods and cleaning products", "description": "laundry detergent washing powder liquid detergent fabric softener dishwashing liquid dish soap floor cleaner surface cleaner bleach disinfectant wipes mops brooms trash bags sponge scourer toilet paper tissue paper paper towels lightbulb led bulb insect spray pest control សាប៊ូបោកខោអាវ ទឹកលាងចាន ទឹកជូតឥដ្ឋ អំពូលភ្លើង"},
    {"division": "06", "code": "06.1.1", "name": "Pharmaceutical products", "description": "pharmaceuticals medicines prescription drugs OTC paracetamol panadol ibuprofen aspirin antibiotics cough syrup cold flu medicine throat lozenges allergy medicine antihistamine antacids vitamins vitamin c multivitamins dietary supplements calcium iron tablets capsules pills eye drops ear drops ថ្នាំ ថ្នាំពេទ្យ ប៉ារ៉ាសេតាម៉ុល វីតាមីន"},
    {"division": "06", "code": "06.1.2", "name": "Other medical products and appliances", "description": "medical bandages gauze adhesive tape antiseptic betadine tiger balm medicated balm plaster thermometer digital thermometer blood pressure monitor omron face masks surgical mask medical gloves rapid test kit covid test crutches wheelchair first aid kit បង់រុំរបួស ប្រេងកូឡា ម៉ាស់"},
    {"division": "07", "code": "07.2.2", "name": "Fuels and lubricants for personal transport equipment", "description": "automotive fuel gasoline petrol super 95 regular gasoline octane 92 diesel fuel engine oil motor oil synthetic oil brake fluid transmission fluid lubricants coolant fuel pump សាំង ប្រេងសាំង ម៉ាស៊ូត ប្រេងម៉ាស៊ូត"},
    {"division": "07", "code": "07.3.2", "name": "Passenger transport by bus and coach", "description": "bus ticket coach ticket intercity bus express bus passenger van transit ticket public transportation bus fare bookmebus redbus fare សំបុត្រឡានក្រុង"},
    {"division": "08", "code": "08.2.0", "name": "Telephone and communication equipment", "description": "mobile phones smartphones smartphone apple iphone iphone 15 pro max samsung galaxy xiaomi oppo vivo feature phone cellular phone tablet cellular handset wireless telephone ទូរស័ព្ទ ទូរស័ព្ទដៃ"},
    {"division": "08", "code": "08.3.0", "name": "Telephone and internet services", "description": "sim card top-up card phone scratch card mobile data plan cellular data subscription vip data voice pack fiber internet home wifi broadband subscription telecom bill cellcard smart metfone ស៊ីមកាត កាតទូរស័ព្ទ អ៊ីនធឺណិត"},
    {"division": "09", "code": "09.1.1", "name": "Equipment for sound and picture", "description": "television tv smart tv 4k tv audio speakers bluetooth speaker wireless soundbar headphones noise cancelling earphones earbuds sony wh-1000xm5 airpods digital camera camcorder projector home theater ទូរទស្សន៍ កាស ធុងបាស"},
    {"division": "09", "code": "09.1.3", "name": "Information processing equipment", "description": "computer laptop notebook pc desktop computer macbook ipad tablet pc monitor computer mouse keyboard external hard drive ssd usb flash drive printer scanner computer accessories កុំព្យូទ័រ កុំព្យូទ័រយួរដៃ"},
    {"division": "09", "code": "09.3.1", "name": "Games, toys and hobbies", "description": "toys children toys building blocks lego action figures dolls board games puzzles video game console playstation nintendo xbox gaming controller sports equipment soccer ball basketball tennis racket dumbbells fitness gear pet food dog food cat food ប្រដាប់ក្មេងលេង"},
    {"division": "09", "code": "09.5.1", "name": "Books and stationery", "description": "books fiction non-fiction textbooks notebooks notepad stationery ballpoint pens pens pencils highlighter scissors stapler printer paper office supplies art supplies សៀវភៅ ប៊ិច"},
    {"division": "10", "code": "10.1.0", "name": "Education services", "description": "school tuition fees primary secondary high school private tutoring english language courses university semester fees course tuition vocational training educational textbooks and schooling supplies ការអប់រំ សាលារៀន សាកលវិទ្យាល័យ"},
    {"division": "11", "code": "11.1.1", "name": "Restaurants and cafes", "description": "restaurant food service cafe dining establishment coffee shop latte cappuccino espresso dine-in buffet table service dining bill restaurant order delivery catering food court service អាហារដ្ឋាន ហាងកាហ្វេ"},
    {"division": "11", "code": "11.2.0", "name": "Accommodation services", "description": "hotel room accommodation luxury hotel suite resort room booking overnight stay sokha hotel hyatt hotel bayon bkk guest house motel room lodging reservation សណ្ឋาគារ"},
    {"division": "12", "code": "12.1.1", "name": "Hairdressing and hair care", "description": "shampoo anti-dandruff head and shoulders pantene loreal hair conditioner hair treatment hair mask hair dye hair styling gel wax pomade hair dryer salon service សាប៊ូកក់សក់ ក្រែមបន្ទន់សក់"},
    {"division": "12", "code": "12.1.3", "name": "Personal care, hygiene and cosmetics", "description": "body wash shower gel bath soap facial cleanser face wash cetaphil moisturizer face cream serum sunscreen spf50 biore uv sunblock body lotion hand cream toothpaste colgate sensodyne toothbrush mouthwash dental floss deodorant spray roll-on roll on perfume fragrance cologne baby diapers pampers mamy poko sanitary pads wet wipes cotton pads razor razor blades shaving cream lip balm lipstick makeup mascara powder skincare cosmetics សាប៊ូ សាប៊ូដុសខ្លួន ថ្នាំដុសធ្មេញ ច្រាសដុសធ្មេញ ឡេការពារកម្តៅថ្ងៃ ឡេលាបខ្លួន ក្រែមលាបមុខ ខោទឹកនោម សំឡីអនាម័យ ទឹកអប់"},
    {"division": "12", "code": "12.3.1", "name": "Jewellery, clocks and watches", "description": "jewelry gold silver necklace bracelet ring earrings wrist watch smart watch clock timepieces គ្រឿងអលង្ការ នាឡិកា"},
    {"division": "12", "code": "12.3.2", "name": "Other personal effects", "description": "handbag purse wallet luggage suitcase travel bag belt sunglasses umbrella leather accessories personal items កាបូប"},
]

class HybridCOICOPClassifier:
    """
    Implements a hierarchical, local-first classification system.
    Priority: Purity -> Semantic -> Ollama Classifier -> Ollama Judge -> Gemini Fallback -> Human.
    """

    def __init__(self):
        self.ollama = OllamaClient()
        self.gemini_client = self._init_gemini()
        self.embedder = self._init_embedder()

        # Pre-compute embeddings for reference definitions if embedder is available
        self.ref_embeddings = {}
        if self.embedder:
            self._build_reference_index()

    def _init_gemini(self) -> Any:
        if not HAS_GENAI:
            log.warning("Gemini AI not available. Cloud fallback will be disabled.")
            return None

        api_key = get_key_pool().get_next_key()
        if not api_key:
            log.warning("GEMINI_API_KEY not found in key pool. Cloud fallback disabled.")
            return None

        if HAS_NEW_GENAI:
            return genai.Client(api_key=api_key)
        else:
            genai.configure(api_key=api_key)
            return genai

    def _init_embedder(self) -> Any:
        if not HAS_SENTENCE_TRANSFORMERS:
            log.warning("sentence-transformers not installed. Semantic matching disabled.")
            return None
        try:
            return SentenceTransformer(LOCAL_FALLBACK_MODEL)
        except Exception as e:
            log.error("Failed to load local embedding model: %s", e)
            return None

    def _build_reference_index(self):
        """Embeds all reference definitions for fast cosine similarity."""
        log.info("Building local COICOP reference index...")
        all_refs = COICOP_12_REFERENCE_DEFINITIONS + COICOP_4DIGIT_REFERENCE_DEFINITIONS
        texts = [f"{r['name']}: {r['description']}" for r in all_refs]
        embeddings = self.embedder.encode(texts)

        for i, ref in enumerate(all_refs):
            self.ref_embeddings[ref['code']] = embeddings[i]

    def _check_store_purity(self, store_slug: str) -> tuple[str, str] | None:
        """Tier 1: Deterministic Store Purity."""
        if store_slug in PURE_STORE_MAP:
            return PURE_STORE_MAP[store_slug]
        return None

    def _semantic_match(self, product_name: str) -> tuple[str, str, float] | None:
        """Tier 2: Vector Similarity against reference space."""
        if not self.embedder:
            return None

        prod_emb = self.embedder.encode(product_name)
        best_code = None
        best_sim = -1.0

        for code, ref_emb in self.ref_embeddings.items():
            sim = np.dot(prod_emb, ref_emb) / (np.linalg.norm(prod_emb) * np.linalg.norm(ref_emb))
            if sim > best_sim:
                best_sim = sim
                best_code = code

        if best_code and best_sim > 0.85:
            # Find division from code
            div = best_code.split('.')[0]
            return div, best_code, float(best_sim)

        return None

    def _classify_with_ollama_hierarchical(self, product_name: str, category_native: str) -> dict[str, Any] | None:
        """
        Tier 3a & 3b: Local Reasoning (Classifier -> Judge).
        """
        # 1. Classifier Phase
        classifier_sys = (
            "You are a COICOP Product Classifier. Analyze the product and assign a 4-digit COICOP code.\n"
            "Format your response as JSON: {\"code\": \"XX.X.X\", \"division\": \"XX\", \"reason\": \"...\"}\n"
            "Use the provided reference guidelines. Be precise."
        )
        classifier_prompt = f"Product: {product_name}\nCategory: {category_native}\nAssign COICOP code."

        proposal = self.ollama.generate(classifier_prompt, system_prompt=classifier_sys)
        if not proposal:
            return None

        # 2. Judge Phase
        judge_sys = (
            "You are a COICOP Auditor. You will receive a product and a proposed COICOP code. "
            "Your job is to verify if the code is correct according to the COICOP handbook.\n"
            "Response JSON: {\"approved\": true/false, \"correct_code\": \"XX.X.X\", \"critique\": \"...\", \"confidence\": 0.0-1.0}"
        )
        judge_prompt = f"Product: {product_name}\nProposed Code: {proposal['code']}\nIs this correct?"

        audit = self.ollama.generate(judge_prompt, system_prompt=judge_sys)
        if not audit:
            return proposal # Fallback to proposal if judge fails

        if audit.get("approved") and audit.get("confidence", 0) >= 0.8:
            return {
                "division": proposal["division"],
                "code": proposal["code"],
                "method": "ollama_hierarchical",
                "confidence": audit["confidence"],
                "reason": proposal["reason"]
            }

        return {"conflict": True, "proposal": proposal, "audit": audit}

    def _classify_with_gemini_fallback(self, product_name: str, category_native: str, context: dict) -> dict[str, Any] | None:
        """Tier 3c: Cloud Arbitration (Gemini)."""
        if not self.gemini_client:
            return None

        prompt = (
            f"Arbitrate a COICOP classification conflict.\n"
            f"Product: {product_name}\n"
            f"Native Category: {category_native}\n"
            f"Local AI Proposal: {context.get('proposal', {}).get('code', 'N/A')}\n"
            f"Local AI Audit Critique: {context.get('audit', {}).get('critique', 'N/A')}\n\n"
            "Provide the definitive COICOP 4-digit code and division. "
            "Response JSON: {\"division\": \"XX\", \"code\": \"XX.X.X\", \"confidence\": 0.0-1.0, \"reason\": \"...\"}"
        )

        try:
            if HAS_NEW_GENAI:
                response = self.gemini_client.models.generate_content(
                    model=LLM_MODEL,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(response_mime_type="application/json")
                )
                result = json.loads(response.text)
            else:
                response = self.gemini_client.generate_content(prompt)
                # Simple extraction of JSON from markdown
                text = response.text
                match = re.search(r"\{.*\}", text, re.DOTALL)
                result = json.loads(match.group()) if match else None

            if result:
                result["method"] = "gemini_fallback"
                return result
        except Exception as e:
            log.error("Gemini fallback failed: %s", e)

        return None

    def classify_product(self, product_name: str, store_slug: str, category_native: str = "") -> dict[str, Any]:
        """
        Main classification entry point implementing the tiered flow.
        """
        # Tier 1: Store Purity
        purity = self._check_store_purity(store_slug)
        if purity:
            return {"division": purity[0], "code": purity[1], "method": "store_purity", "confidence": 1.0}

        # Tier 2: Semantic Reference
        semantic = self._semantic_match(product_name)
        if semantic:
            div, code, sim = semantic
            return {"division": div, "code": code, "method": "semantic_vector", "confidence": sim}

        # Tier 3: Hierarchical AI
        ai_result = self._classify_with_ollama_hierarchical(product_name, category_native)
        if ai_result:
            if "conflict" not in ai_result:
                return ai_result

            # Tier 3c: Gemini Arbitration
            gemini_result = self._classify_with_gemini_fallback(product_name, category_native, ai_result)
            if gemini_result and gemini_result.get("confidence", 0) >= 0.7:
                return gemini_result

        # Tier 4: Human Review
        return {
            "division": "UNCLASSIFIED",
            "code": "UNCLASSIFIED",
            "method": "human_review_required",
            "confidence": 0.0
        }


def get_hybrid_classifier() -> HybridCOICOPClassifier:
    """Factory function to get a HybridCOICOPClassifier instance."""
    return HybridCOICOPClassifier()
