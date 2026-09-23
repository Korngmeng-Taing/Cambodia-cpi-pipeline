import os
import json
import pandas as pd
from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types

load_dotenv()
raw_key = os.getenv("GEMINI_API_KEYS", os.getenv("GEMINI_API_KEY", ""))
api_key = [k.strip() for k in raw_key.split(",") if k.strip()][0]
client = genai.Client(api_key=api_key)
model_name = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

SYSTEM_PROMPT = """You are an expert UN COICOP (Classification of Individual Consumption According to Purpose) classification engine for the Consumer Price Index (CPI) in Cambodia.

Classify each consumer product strictly into its official 4-digit COICOP Class code (format DD.G.C):
- 01: Food and non-alcoholic beverages (01.1.1 Bread/cereals, 01.1.4 Milk/dairy, 01.1.8 Confectionery/cookies/nuts, 01.1.9 Food sauces/condiments)
- 02: Alcoholic beverages and tobacco (02.1.1 Spirits/Whiskey, 02.1.3 Beer, 02.2.0 Tobacco/Cigarettes)
- 05: Furnishings and household maintenance (05.3.1 Kitchen appliances, 05.6.1 Cleaning detergents/household vinegar)
- 06: Health (06.1.1 Medicines)
- 09: Recreation and culture (09.3.1 Pets / Pet food)
- 12: Miscellaneous goods and personal care (12.1.3 Baby toiletries, soap, shampoo, hygiene)

Return a strict JSON list of objects:
[
  {
    "id": <int>,
    "product_name": "<name>",
    "coicop_division": "<2-digit>",
    "coicop_code": "<4-digit>",
    "category_name": "<title>",
    "reason": "<short justification>"
  }
]
"""

# The Famous Confusion Words from our Critical Traps
confusion_products = [
    {"id": 1, "product_name": "Bourbon Chocochip Cookies 100g"},
    {"id": 2, "product_name": "Camel Roasted Salted Peanuts 150g"},
    {"id": 3, "product_name": "Cleaning White Vinegar 1 Liter"},
    {"id": 4, "product_name": "Hot Pot Soup Base Spicy Seasoning 200g"},
    {"id": 5, "product_name": "Baby Oil Sensitive Skin 200ml"},
    {"id": 6, "product_name": "Pedigree Dog Food Chunks in Gravy 400g"},
    {"id": 7, "product_name": "Apple Cider Vinegar 500ml"},
    {"id": 8, "product_name": "Jim Beam Kentucky Bourbon Whiskey 750ml"},
    {"id": 9, "product_name": "Camel Filter Cigarettes 20s"},
    {"id": 10, "product_name": "Electric Hot Pot Cooker 5 Liter"}
]

print("Sending 10 Confusion Products to Gemini AI...")
response = client.models.generate_content(
    model=model_name,
    contents=json.dumps(confusion_products, ensure_ascii=False, indent=2),
    config=genai_types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        temperature=0.0
    )
)

data = json.loads(response.text)
df = pd.DataFrame(data)
print("\n" + "="*80)
print("GEMINI AI CLASSIFICATION ON CONFUSION WORDS:")
print("="*80)
print(df[["product_name", "coicop_division", "coicop_code", "category_name", "reason"]].to_string(index=False))
