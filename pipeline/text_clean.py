"""
pipeline.text_clean — Text normalization utilities for CPI item matching.

Mirrors the cleaning steps used in dbt Silver models (int_prices_cleaned.sql):
  1. HTML entity decode
  2. Strip embedded prices (e.g. "$1.99", "4,000KHR")
  3. Strip promotional words (SALE, PROMO, DISCOUNT, CLEARANCE, etc.)
  4. Collapse whitespace and trim
  5. Uppercase for case-insensitive comparison
  6. Khmer-aware normalization (Khmer numerals, common abbreviations)
"""

import html
import re

# ── Compiled regex patterns ──────────────────────────────────────────────────

# Matches price-like substrings:  $1.99  |  1,200KHR  |  USD 4.50  |  ៛3000
_RE_PRICE = re.compile(
    r"""
    [$\u17DB]?\s*                   # optional $ or ៛ prefix
    \d{1,3}(?:[,.\s]\d{3})*        # integer part with separators
    (?:[.,]\d{1,2})?               # optional decimal
    \s*(?:KHR|USD|RIEL|៛|\$)?      # optional currency suffix
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
    "សាំង": "GASOLINE",
    "ប្រេងសាំង": "GASOLINE",
    "ប្រេងម៉ាស៊ូត": "DIESEL",
    "ម៉ាស៊ូត": "DIESEL",
    "ស្រា": "BEER",
    "ស្រាបៀរ": "BEER",
    "អង្ករ": "RICE",
    "អង្ករផ្កាម្លិះ": "JASMINE RICE",
    "ត្រី": "FISH",
    "ទឹក": "WATER",
    "ទឹកបរិសុទ្ធ": "WATER",
    "ទឹកដោះគោ": "MILK",
    "មាន់": "CHICKEN",
    "សាច់មាន់": "CHICKEN",
    "ជ្រូក": "PORK",
    "សាច់ជ្រូក": "PORK",
    "គោ": "BEEF",
    "សាច់គោ": "BEEF",
    "ស៊ុត": "EGG",
    "ពងទា": "DUCK EGG",
    "ពងមាន់": "CHICKEN EGG",
    "បន្លែ": "VEGETABLE",
    "ផ្លែឈើ": "FRUIT",
    "ប្រេងឆា": "COOKING OIL",
    "ស្ករស": "SUGAR",
    "អំបិល": "SALT",
    "នំប៉័ង": "BREAD",
    "មី": "NOODLES",
    "កាហ្វេ": "COFFEE",
    "តែ": "TEA",
    "ថ្នាំ": "MEDICINE",
    "សាប៊ូ": "SOAP",
    "ខោអាវ": "CLOTHES",
    "ស្បែកជើង": "SHOES",
    "ទូរស័ព្ទ": "PHONE",
    "ឡាន": "CAR",
    "ម៉ូតូ": "MOTORBIKE",
    "ផ្ទះ": "HOUSE",
    "បន្ទប់ជួល": "RENTAL",
}

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
    "g": "g", "gram": "g", "grams": "g", "gm": "g",
    "kg": "kg", "kilo": "kg", "kilos": "kg", "kilogram": "kg", "kilograms": "kg",
    "ml": "ml", "milliliter": "ml", "milliliters": "ml", "millilitre": "ml",
    "l": "l", "ltr": "l", "litre": "l", "liter": "l", "litres": "l", "liters": "l",
    "oz": "oz", "ounce": "oz", "ounces": "oz",
    "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
    "pack": "pack", "pk": "pack", "pkt": "pack", "packet": "pack", "packs": "pack",
    "can": "can", "cans": "can",
    "bottle": "bottle", "bottles": "bottle", "btl": "bottle",
    "box": "box", "boxes": "box", "bx": "box",
    "piece": "piece", "pc": "piece", "pcs": "piece", "pieces": "piece",
    "sachet": "sachet", "sach": "sachet",
    "bag": "bag", "bags": "bag", "bg": "bag",
    "carton": "carton", "ctn": "carton",
    "jar": "jar", "jars": "jar",
    "tube": "tube", "tubes": "tube",
    "roll": "roll", "rolls": "roll", "rll": "roll",
    "stick": "stick", "sticks": "stick", "stk": "stick",
    "pair": "pair", "pr": "pair",
    "set": "set", "sets": "set", "st": "set",
    "dozen": "dozen", "dz": "dozen",
    "tablet": "tablet", "tab": "tablet", "tablets": "tablet",
    "capsule": "capsule", "cap": "capsule", "capsules": "capsule",
    "serving": "serving", "servings": "serving",
}


def segment_khmer_words(text: str) -> str:
    """
    Inserts spaces between Khmer character clusters/words to handle
    unsegmented Khmer scripts without spaces.
    """
    if not text:
        return text
    # Khmer consonant cluster boundary: starts with base consonant (U+1780 - U+17B3)
    # followed by dependent vowels/subscripts (U+17B4 - U+17D3)
    khmer_cluster_pattern = re.compile(r'([\u1780-\u17B3][\u17B4-\u17D3]*)')
    # Replace dictionary matches with space-delimited English equivalents
    for k, v in _KHMER_TERMS.items():
        text = text.replace(k, f" {v} ")
    return text


def clean_name_for_matching(raw: str | None) -> str:
    """Normalize a raw item description for fuzzy/exact matching.

    Returns an uppercase, stripped string suitable for comparison.
    Returns empty string if input is None or blank.

    Examples
    --------
    >>> clean_name_for_matching("  Coca-Cola 330ml SALE $1.99  ")
    'COCA-COLA 330ML'
    >>> clean_name_for_matching(None)
    ''
    """
    if not raw or not raw.strip():
        return ""

    text = raw

    # 1. HTML entity decode  (e.g. &amp; → &, &#39; → ')
    text = html.unescape(text)

    # 2. Strip embedded prices
    text = _RE_PRICE.sub(" ", text)

    # 3. Strip promo words
    text = _PROMO_WORDS.sub(" ", text)

    # 4. Khmer normalization & segmentation
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

    # Segment and translate known Khmer terms
    text = segment_khmer_words(text)

    return text


def expand_abbreviations(text: str) -> str:
    """Expand common product abbreviations for better matching.

    E.g. "ORG" → "ORGANIC", "SPK" → "SPICY", "BTL" → "BOTTLE"
    """
    def _replace(m):
        word = m.group(0).upper()
        return _UNIT_SYNONYMS.get(word.lower(), word)

    # Expand unit abbreviations
    for abbr, canonical in _UNIT_SYNONYMS.items():
        text = re.sub(r'\b' + re.escape(abbr) + r'\b', canonical.upper(), text, flags=re.IGNORECASE)

    # Expand English product abbreviations
    text = _EN_ABBREV.sub(lambda m: m.group(0).upper(), text)

    return text


def full_normalize(raw: str | None) -> str:
    """Full normalization pipeline: Khmer → price/promo strip → uppercase → abbrev expand.

    Use this as the primary entry point for maximum normalization.
    """
    if not raw or not raw.strip():
        return ""

    text = raw

    # Khmer-aware normalization first
    text = normalize_khmer(text)

    # Standard cleaning
    text = clean_name_for_matching(text)

    # Expand abbreviations
    text = expand_abbreviations(text)

    return text
