"""
pipeline.text_clean — Text normalization utilities for CPI item matching.

Mirrors the cleaning steps used in dbt Silver models (int_prices_cleaned.sql):
  1. HTML entity decode
  2. Strip embedded prices (e.g. "$1.99", "4,000KHR") — but NOT package sizes
  3. Strip promotional words (SALE, PROMO, DISCOUNT, CLEARANCE, etc.)
  4. Collapse whitespace and trim
  5. Uppercase for case-insensitive comparison
  6. Khmer-aware normalization (Khmer numerals, common abbreviations)
"""

import html
import re

# ── Compiled regex patterns ──────────────────────────────────────────────────

# Matches ONLY true price substrings:  $1.99  |  1,200KHR  |  USD 4.50  |  ៛3000
# C2 fix: previously the suffix was optional, so bare "<digits><letters>" like
# "330ml" / "500g" matched and got stripped from product names. The regex now
# REQUIRES an explicit currency prefix OR suffix — never matches a bare number
# followed by a unit. Package size (ml/g/kg/lb/oz) is preserved in the cleaned
# name; `raw_payload.package_size` remains the contract for unit normalization.
_RE_PRICE = re.compile(
    r"""
    (?:                              # one of two anchors required:
        [$៛]\s*                 #   prefix: $ or ៛
        \d{1,9}(?:[,.\s]\d{3})*      #   integer part (1-9 digits; opt. thousands)
        (?:[.,]\d{1,2})?             #   optional decimal
    )
    |
    (?:                              # OR explicit currency suffix:
        \d{1,9}(?:[,.\s]\d{3})*      #   integer part (1-9 digits; opt. thousands)
        (?:[.,]\d{1,2})?             #   optional decimal
        \s*(?:KHR|USD|RIEL|៛|\$) #   required currency suffix
    )
    |
    (?:                              # OR currency-word prefix "USD 1.99" or "USD1.99":
        (?:KHR|USD|RIEL)\s*      #   required currency prefix token (opt. space)
        \d{1,9}(?:[,.\s]\d{3})*      #   integer part (1-9 digits; opt. thousands)
        (?:[.,]\d{1,2})?             #   optional decimal
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Common promotional / noise words to strip
_PROMO_WORDS = re.compile(
    r"\b(?:SALE|PROMO|PROMOTION|DISCOUNT|CLEARANCE|HOT\s*DEAL|BEST\s*SELLER"
    r"|NEW\s*ARRIVAL|LIMITED|SPECIAL\s*OFFER|FLASH\s*SALE|BUY\s*\d+\s*GET\s*\d+"
    r"|FREE\s*SHIPPING|BUNDLE)\b",
    re.IGNORECASE,
)

# Collapse multiple whitespace characters into one space
_RE_MULTI_SPACE = re.compile(r"\s+")

# Strip non-alphanumeric characters at start/end
_RE_TRIM_NOISE = re.compile(r"^[\s\-–—•·|/\\]+|[\s\-–—•·|/\\]+$")

# Khmer numeral to Arabic mapping
_KHMER_DIGITS = str.maketrans("០១២៣៤៥៦៧៨៩", "0123456789")

# Comprehensive Khmer dictionary mappings (Khmer UTF-8 → English standard terms)
_KHMER_TERMS = {
    # Automotive / Energy (Div 07 / 04)
    "សាំង": "GASOLINE",
    "ប្រេងសាំង": "GASOLINE",
    "ប្រេងម៉ាស៊ូត": "DIESEL",
    "ម៉ាស៊ូត": "DIESEL",
    "ហ្គាស": "COOKING GAS",
    "អគ្គិសនី": "ELECTRICITY",
    "ទឹកស្អាត": "TAP WATER",

    # Alcohol & Tobacco (Div 02)
    "ស្រា": "BEER",
    "ស្រាបៀរ": "BEER",
    "ស្រាបៀរអង្គរ": "ANGKOR BEER",
    "ស្រាក្រហម": "RED WINE",
    "ស្រាស": "WHITE WINE",
    "ស្រាវីស្គី": "WHISKEY",
    "បារី": "CIGARETTES",

    # Rice, Grains, Bakery (Div 01.1.1)
    "អង្ករ": "RICE",
    "អង្ករផ្កាម្លិះ": "JASMINE RICE",
    "នំប៉័ង": "BREAD",
    "មី": "NOODLES",
    "ម្សៅ": "FLOUR",
    "ម្សៅមី": "WHEAT FLOUR",

    # Meat & Poultry (Div 01.1.2)
    "សាច់គោ": "BEEF",
    "សាច់គោស្រស់": "FRESH BEEF",
    "គោ": "BEEF",
    "សាច់ជ្រូក": "PORK",
    "សាច់ជ្រូកស្រស់": "FRESH PORK",
    "ជ្រូក": "PORK",
    "សាច់មាន់": "CHICKEN",
    "សាច់មាន់ស្រស់": "FRESH CHICKEN",
    "មាន់": "CHICKEN",
    "សាច់ទា": "DUCK",
    "សាច់ក្រក": "SAUSAGE",

    # Fish & Seafood (Div 01.1.3)
    "ត្រី": "FISH",
    "ត្រីស្រស់": "FRESH FISH",
    "ត្រីសាម៉ុង": "SALMON",
    "ត្រីសាម៉ុងស្រស់": "FRESH SALMON",
    "ត្រីធូណា": "TUNA",
    "បង្គា": "SHRIMP",
    "មឹក": "SQUID",
    "ក្តាម": "CRAB",
    "ប្រហុក": "FERMENTED FISH",

    # Dairy & Eggs (Div 01.1.4)
    "ទឹកដោះគោ": "MILK",
    "ទឹកដោះគោស្រស់": "FRESH MILK",
    "ទឹកដោះគោឆៅ": "RAW MILK",
    "ឈីស": "CHEESE",
    "ប៊ឺ": "BUTTER",
    "យ៉ាអួ": "YOGURT",
    "ស៊ុត": "EGG",
    "ពងទា": "DUCK EGG",
    "ពងមាន់": "CHICKEN EGG",

    # Oils & Fats (Div 01.1.5)
    "ប្រេងឆា": "COOKING OIL",
    "ប្រេងដូង": "COCONUT OIL",
    "ប្រេងអូលីវ": "OLIVE OIL",

    # Fruit (Div 01.1.6)
    "ផ្លែឈើ": "FRUIT",
    "ផ្លែប៉ោម": "APPLE",
    "ផ្លែចេក": "BANANA",
    "ចេក": "BANANA",
    "ផ្លែក្រូច": "ORANGE",
    "ក្រូច": "ORANGE",
    "ផ្លែស្វាយ": "MANGO",
    "ស្វាយ": "MANGO",
    "ឪឡឹក": "WATERMELON",
    "ទំពាំងបាយជូរ": "GRAPES",

    # Vegetables (Div 01.1.7)
    "បន្លែ": "VEGETABLE",
    "ប៉េងប៉ោះ": "TOMATO",
    "ដំឡូងបារាំង": "POTATO",
    "ខ្ទឹមបារាំង": "ONION",
    "ខ្ទឹមស": "GARLIC",
    "ម្ទេស": "CHILI",
    "ការ៉ុត": "CARROT",

    # Sugar, Sweets & Spices (Div 01.1.8 / 01.1.9)
    "ស្ករស": "SUGAR",
    "ស្ករត្នោត": "PALM SUGAR",
    "ទឹកឃ្មុំ": "HONEY",
    "សូកូឡា": "CHOCOLATE",
    "ស្ករគ្រាប់": "CANDY",
    "នំ": "CAKE",
    "នំស្រួយ": "BISCUITS",
    "អំបិល": "SALT",
    "ទឹកត្រី": "FISH SAUCE",
    "ទឹកស៊ីអ៊ីវ": "SOY SAUCE",
    "គ្រឿងទេស": "SPICES",

    # Beverages (Div 01.2.1 / 01.2.2)
    "កាហ្វេ": "COFFEE",
    "តែ": "TEA",
    "កាកាវ": "COCOA",
    "ទឹក": "WATER",
    "ទឹកបរិសុទ្ធ": "WATER",
    "ទឹកក្រូច": "SOFT DRINK",
    "កូកាកូឡា": "COCA COLA",
    "ទឹកផ្លែឈើ": "FRUIT JUICE",

    # Clothing & Footwear (Div 03)
    "ខោអាវ": "CLOTHES",
    "អាវ": "SHIRT",
    "អាវយឺត": "T-SHIRT",
    "ខោ": "PANTS",
    "ខោខូវប៊យ": "JEANS",
    "រ៉ូប": "DRESS",
    "សំពត់": "SKIRT",
    "អាវរងា": "JACKET",
    "ស្រោមជើង": "SOCKS",
    "ស្បែកជើង": "SHOES",
    "ស្បែកជើងប៉ាតា": "SNEAKERS",
    "ស្បែកជើងផ្ទាត់": "SLIPPERS",

    # Housing & Furnishing (Div 04 / 05)
    "ផ្ទះ": "HOUSE",
    "បន្ទប់ជួល": "RENTAL",
    "ផ្ទះជួល": "HOUSE RENTAL",
    "តុ": "TABLE",
    "កៅអី": "CHAIR",
    "គ្រែ": "BED",
    "ពូក": "MATTRESS",
    "ភួយ": "BLANKET",
    "កន្សែង": "TOWEL",
    "កម្រាលពូក": "BEDSHEET",
    "សាប៊ូបោកខោអាវ": "LAUNDRY DETERGENT",
    "ទឹកលាងចាន": "DISHWASHING LIQUID",
    "ទឹកជូតឥដ្ឋ": "FLOOR CLEANER",
    "អំពូលភ្លើង": "LIGHT BULB",

    # Health (Div 06)
    "ថ្នាំ": "MEDICINE",
    "ថ្នាំពេទ្យ": "MEDICINE",
    "ប៉ារ៉ាសេតាម៉ុល": "PARACETAMOL",
    "វីតាមីន": "VITAMINS",
    "បង់រុំរបួស": "BANDAGE",
    "ប្រេងកូឡា": "MEDICATED BALM",
    "ម៉ាស់": "FACE MASK",

    # Communication & Tech (Div 08 / 09)
    "ទូរស័ព្ទ": "PHONE",
    "ទូរស័ព្ទដៃ": "MOBILE PHONE",
    "ស៊ីមកាត": "SIM CARD",
    "កាតទូរស័ព្ទ": "PHONE CARD",
    "អ៊ីនធឺណិត": "INTERNET",
    "កុំព្យូទ័រ": "COMPUTER",
    "កុំព្យូទ័រយួរដៃ": "LAPTOP",
    "ទូរទស្សន៍": "TELEVISION",
    "កាស": "HEADPHONES",
    "ធុងបាស": "SPEAKER",
    "ឆ្នាំងសាក": "CHARGER",
    "ខ្សែសាក": "CHARGING CABLE",
    "សៀវភៅ": "BOOK",
    "ប៊ិច": "PEN",
    "ប្រដាប់ក្មេងលេង": "TOYS",

    # Transport & Hospitality (Div 07 / 11)
    "ឡាន": "CAR",
    "ម៉ូតូ": "MOTORBIKE",
    "សំបុត្រឡានក្រុង": "BUS TICKET",
    "សណ្ឋាគារ": "HOTEL",
    "អាហារដ្ឋាន": "RESTAURANT",
    "ហាងកាហ្វេ": "CAFE",

    # Personal Care (Div 12)
    "សាប៊ូ": "SOAP",
    "សាប៊ូកក់សក់": "SHAMPOO",
    "ក្រែមបន្ទន់សក់": "HAIR CONDITIONER",
    "សាប៊ូដុសខ្លួន": "BODY WASH",
    "ថ្នាំដុសធ្មេញ": "TOOTHPASTE",
    "ច្រាសដុសធ្មេញ": "TOOTHBRUSH",
    "ឡេការពារកម្តៅថ្ងៃ": "SUNSCREEN",
    "ឡេលាបខ្លួន": "BODY LOTION",
    "ក្រែមលាបមុខ": "FACE CREAM",
    "ខោទឹកនោម": "DIAPERS",
    "សំឡីអនាម័យ": "SANITARY PADS",
    "ទឹកអប់": "PERFUME",
    "កាបូប": "BAG",
    "នាឡិកា": "WATCH",
    "គ្រឿងអលង្ការ": "JEWELRY",
}


def is_khmer_text(text: str) -> bool:
    """Returns True if the text contains Khmer unicode characters (\u1780-\u17ff)."""
    if not text:
        return False
    return bool(re.search(r"[\u1780-\u17ff]", text))


def extract_khmer_tokens(text: str) -> list[str]:
    """Extracts known Khmer compound tokens and unsegmented Khmer morphemes."""
    if not text or not is_khmer_text(text):
        return []
    tokens = []
    # 1. Match known dictionary compounds longest-first
    remaining = text
    for k in sorted(_KHMER_TERMS.keys(), key=len, reverse=True):
        if k in remaining:
            tokens.append(k)
            eng_equiv = _KHMER_TERMS[k].lower()
            tokens.extend(eng_equiv.split())
    # 2. Extract any individual Khmer character clusters
    khmer_clusters = re.findall(r"[\u1780-\u17ff]+", text)
    for cl in khmer_clusters:
        if cl not in tokens:
            tokens.append(cl)
    return tokens

# Common English abbreviations to expand
_EN_ABBREV = re.compile(
    r"\b(?:SPK|SPICY|ORG|ORGANIC|LOW\s*SODIUM|LS|FF|FAT\s*FREE|SKIM|WHOLE"
    r"|LT|LIGHT|REG|REGULAR|FAM|FAMILY|XL|XXL|SM|SMALL|MED|MEDIUM|LG|LARGE"
    r"|PKT|PACK|PK|PKG|BTL|BOTTLE|JAR|TUB|BOX|CAN|BAG|SAC|BUNCH|EACH"
    r"|SP|SPECIAL|NWT|NEW|DLX|DELUXE|PREM|PREMIUM|ORIG|ORIGINAL"
    r"|F/FL|FULL\s*FLAVOR|SSL|SOFT\s*PACK|HARDSHELL|H/S|K/LESS|KING\s*SIZE"
    r"|MULTI|ASSORTED|VARIOUS|MIXED)\b",
    re.IGNORECASE,
)

# Unit synonyms → canonical form (for Python-side matching)
_UNIT_SYNONYMS = {
    "g": "g",
    "gram": "g",
    "grams": "g",
    "gm": "g",
    "kg": "kg",
    "kilo": "kg",
    "kilos": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "ml": "ml",
    "milliliter": "ml",
    "milliliters": "ml",
    "millilitre": "ml",
    "l": "l",
    "ltr": "l",
    "litre": "l",
    "liter": "l",
    "litres": "l",
    "liters": "l",
    "oz": "oz",
    "ounce": "oz",
    "ounces": "oz",
    "lb": "lb",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
    "pack": "pack",
    "pk": "pack",
    "pkt": "pack",
    "packet": "pack",
    "packs": "pack",
    "can": "can",
    "cans": "can",
    "bottle": "bottle",
    "bottles": "bottle",
    "btl": "bottle",
    "box": "box",
    "boxes": "box",
    "bx": "box",
    "piece": "piece",
    "pc": "piece",
    "pcs": "piece",
    "pieces": "piece",
    "sachet": "sachet",
    "sach": "sachet",
    "bag": "bag",
    "bags": "bag",
    "bg": "bag",
    "carton": "carton",
    "ctn": "carton",
    "jar": "jar",
    "jars": "jar",
    "tube": "tube",
    "tubes": "tube",
    "roll": "roll",
    "rolls": "roll",
    "rll": "roll",
    "stick": "stick",
    "sticks": "stick",
    "stk": "stick",
    "pair": "pair",
    "pr": "pair",
    "set": "set",
    "sets": "set",
    "st": "set",
    "dozen": "dozen",
    "dz": "dozen",
    "tablet": "tablet",
    "tab": "tablet",
    "tablets": "tablet",
    "capsule": "capsule",
    "cap": "capsule",
    "capsules": "capsule",
    "serving": "serving",
    "servings": "serving",
}


# Product abbreviation expansion dictionary
_PRODUCT_ABBREVIATIONS = {
    "SPK": "SPICY",
    "ORG": "ORGANIC",
    "LS": "LOW SODIUM",
    "FF": "FAT FREE",
    "LT": "LIGHT",
    "REG": "REGULAR",
    "FAM": "FAMILY",
    "SM": "SMALL",
    "MED": "MEDIUM",
    "LG": "LARGE",
    "PKT": "PACK",
    "PK": "PACK",
    "PKG": "PACK",
    "BTL": "BOTTLE",
    "DLX": "DELUXE",
    "PREM": "PREMIUM",
    "ORIG": "ORIGINAL",
    "CTN": "CARTON",
    "PCS": "PIECES",
    "PC": "PIECE",
}


def segment_khmer_words(text: str) -> str:
    """
    Inserts spaces around translated Khmer dictionary words while preserving
    Khmer unicode character sequences.

    C9 / H9 hardening: dictionary keys are applied LONGEST-FIRST so that
    'ទឹកដោះគោ' (MILK) wins over 'ទឹក' (WATER) + 'គោ' (BEEF). Without this
    ordering, 'ទឹកដោះគោ' was rewritten to 'WATER MILK BEEF' (compound split),
    which then deduped every Khmer grocery against the WATER/BEEF canonicals.
    """
    if not text:
        return text
    # Longest-first so multi-character compounds match before single chars.
    for k in sorted(_KHMER_TERMS.keys(), key=len, reverse=True):
        text = text.replace(k, f" {_KHMER_TERMS[k]} ")
    return re.sub(r"\s+", " ", text).strip()


def clean_name_for_matching(raw: str | None) -> str:
    """Normalize a raw item description for fuzzy/exact matching.

    Returns an uppercase, stripped string suitable for comparison.
    Returns empty string if input is None or blank.

    Package sizes (e.g. "330ml", "500g") are preserved; only true currency
    prices (anchored by $ / ៛ / USD / KHR / RIEL) are stripped.

    Examples
    --------
    >>> clean_name_for_matching("  Coca-Cola 330ml SALE $1.99  ")
    'COCA-COLA 330ML'
    >>> clean_name_for_matching("Coca-Cola 500g")
    'COCA-COLA 500G'
    >>> clean_name_for_matching(None)
    ''
    """
    if not raw or not raw.strip():
        return ""

    text = raw

    # 1. HTML entity decode  (e.g. &amp; → &, #39; → ')
    text = html.unescape(text)

    # 2. Strip embedded prices (requires explicit currency anchor — package
    #    sizes like "330ml" are NOT matched by the new _RE_PRICE pattern).
    text = _RE_PRICE.sub(" ", text)

    # 3. Strip promo words
    text = _PROMO_WORDS.sub(" ", text)

    # 4. Khmer normalization & segmentation (longest-first, see H9 fix)
    text = segment_khmer_words(text)
    text = text.translate(_KHMER_DIGITS)

    # 5. Collapse whitespace & trim
    text = _RE_MULTI_SPACE.sub(" ", text).strip()

    # 6. Remove leading/trailing noise chars
    text = _RE_TRIM_NOISE.sub("", text).strip()

    # 7. Uppercase
    text = text.upper()

    return text


def normalize_khmer(text: str) -> str:
    """Khmer-aware normalization: convert Khmer numerals to Arabic,
    segment Khmer compounds, and translate common terms.
    """
    if not text:
        return text

    # Convert Khmer numerals to Arabic
    text = text.translate(_KHMER_DIGITS)

    # Segment and translate known Khmer terms (longest-first)
    text = segment_khmer_words(text)

    return text


# Pre-compiled combined alternation regex for unit synonyms — sorted longest-first
# so multi-character tokens (e.g. "millilitre") match before single-char ones ("l").
# Built once at module load; reused across all expand_abbreviations() calls.
_UNIT_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(_UNIT_SYNONYMS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

# Pre-compiled combined alternation regex for product abbreviations.
_ABBREV_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(_PRODUCT_ABBREVIATIONS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def expand_abbreviations(text: str) -> str:
    """Expand common product and unit abbreviations for better matching.

    E.g. "ORG" → "ORGANIC", "SPK" → "SPICY", "BTL" → "BOTTLE"
    """
    if not text:
        return ""

    def _replace_unit(m: re.Match) -> str:
        return _UNIT_SYNONYMS.get(m.group(1).lower(), m.group(1)).upper()

    def _replace_abbrev(m: re.Match) -> str:
        return _PRODUCT_ABBREVIATIONS.get(m.group(1).upper(), m.group(1))

    text = _UNIT_PATTERN.sub(_replace_unit, text)
    text = _ABBREV_PATTERN.sub(_replace_abbrev, text)
    return re.sub(r"\s+", " ", text).strip()


def full_normalize(raw: str | None) -> str:
    """Full normalization pipeline: Khmer → price/promo strip → uppercase → abbrev expand.

    Use this as the primary entry point for maximum normalization.
    Package sizes are preserved.
    """
    if not raw or not raw.strip():
        return ""

    text = raw

    # Khmer-aware normalization first
    text = normalize_khmer(text)

    # Standard cleaning (preserves package sizes)
    text = clean_name_for_matching(text)

    # Expand abbreviations
    text = expand_abbreviations(text)

    return text


# ──────────────────────────────────────────────────────────────────────────────
# Shared size compatibility (H2 fix) — used by both item_matcher and
# vector_item_matcher so g↔kg and ml↔L cross-normalization is consistent.
# ──────────────────────────────────────────────────────────────────────────────

_SIZE_FACTORS = {
    "ml": 0.001,
    "l": 1.0,
    "g": 0.001,
    "kg": 1.0,
}

_UNIT_DIMENSION = {
    "ml": "volume",
    "l": "volume",
    "g": "mass",
    "kg": "mass",
}

def is_size_compatible(
    size1: str | None, size2: str | None, tolerance: float = 0.10
) -> bool:
    """Check if two package sizes are compatible within a relative tolerance.

    Cross-normalizes g↔kg and ml↔L so "100g" matches "0.1kg" and "330ml"
    matches "0.33L". Returns True if either size is blank/None (permissive).
    """
    if not size1 or not size2:
        return True

    s1 = size1.strip().lower()
    s2 = size2.strip().lower()

    if s1 == s2:
        return True

    m1 = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]+)$", s1)
    m2 = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]+)$", s2)

    if m1 and m2:
        v1, u1 = float(m1.group(1)), m1.group(2)
        v2, u2 = float(m2.group(1)), m2.group(2)

        if v1 > 0 and v2 > 0:
            f1 = _SIZE_FACTORS.get(u1)
            f2 = _SIZE_FACTORS.get(u2)

            # Cross-normalize if same dimension (volume↔volume, mass↔mass)
            if f1 is not None and f2 is not None and _UNIT_DIMENSION.get(u1) == _UNIT_DIMENSION.get(u2):
                b1, b2 = v1 * f1, v2 * f2
                diff = abs(b1 - b2) / max(b1, b2)
                return diff <= tolerance

            # Same unit string — direct comparison
            if u1 == u2:
                diff = abs(v1 - v2) / max(v1, v2)
                return diff <= tolerance

    return False
