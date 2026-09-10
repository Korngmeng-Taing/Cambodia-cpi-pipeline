import requests
import json
import re
import os
from typing import List, Dict

# --- Helper to read .env ---
def load_env_var(var_name: str) -> str:
    try:
        with open(".env", "r") as f:
            for line in f:
                if line.startswith(var_name + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""

# --- Configuration ---
GEMINI_KEYS_STR = load_env_var("GEMINI_API_KEYS")
GEMINI_KEYS = GEMINI_KEYS_STR.split(",") if GEMINI_KEYS_STR else []
GEMINI_MODEL = load_env_var("GEMINI_MODEL") or "gemini-3.1-flash-lite"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

# Ollama Config
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODELS = {
    "Llama3.1": "llama3.1:latest",
    "Qwen3": "qwen3:8b"
}

# Test dataset: (Product Name, Expected Division)
TEST_PRODUCTS = [
    ("3D White Vivid Mint Toothpaste - Crest", "12"),
    ("Panasonic Hair Dryer", "12"),
    ("Somersby Cider 4x330ml", "02"),
    ("Samyang Spicy Beef Hot Pot", "01"),
    ("Tuk Tuk Transport Fare", "07"),
    ("Hospital Consultation Fee", "06"),
    ("iPhone 15 Pro Max", "08"),
    ("Lix Floor Cleaner 3.8L", "05"),
    ("Cinema Ticket", "09"),
    ("Hyatt Hotel Room", "11"),
]

def call_gemini(product_name: str) -> str:
    if not GEMINI_KEYS:
        return "ERR(NO_KEY)"

    key = GEMINI_KEYS[0] # Use first key for benchmark

    prompt = f"""You are a COICOP classification expert.
Classify the following product into one of the 12 COICOP divisions:
01: Food, beverages and tobacco
02: Alcoholic beverages, tobacco and narcotics
03: Clothing and footwear
04: Housing, water, electricity, gas and other fuels
05: Furnishings, household equipment and routine maintenance
06: Health
07: Transport
08: Communications
09: Recreation and culture
10: Education
11: Restaurants and hotels
12: Other goods and services

Product: {product_name}

Return ONLY the 2-digit division code. No explanation. No punctuation.
Example: 01"""

    url = GEMINI_URL.format(model=GEMINI_MODEL, key=key)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        text = data['candidates'][0]['content']['parts'][0]['text'].strip()
        match = re.search(r'\d{2}', text)
        return match.group(0) if match else "ERR"
    except Exception as e:
        return f"ERR({type(e).__name__})"

def call_ollama(model_name: str, product_name: str) -> str:
    prompt = f"""You are a COICOP classification expert.
Classify the following product into one of the 12 COICOP divisions:
01: Food, beverages and tobacco
02: Alcoholic beverages, tobacco and narcotics
03: Clothing and footwear
04: Housing, water, electricity, gas and other fuels
05: Furnishings, household equipment and routine maintenance
06: Health
07: Transport
08: Communications
09: Recreation and culture
10: Education
11: Restaurants and hotels
12: Other goods and services

Product: {product_name}

Return ONLY the 2-digit division code. No explanation. No punctuation.
Example: 01"""

    try:
        response = requests.post(OLLAMA_URL, json={
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0}
        }, timeout=30)
        response.raise_for_status()
        text = response.json().get("response", "").strip()
        match = re.search(r'\d{2}', text)
        return match.group(0) if match else "ERR"
    except Exception as e:
        return f"ERR({type(e).__name__})"

def main():
    results = []
    print(f"Testing {len(TEST_PRODUCTS)} products across 3 LLMs (Standalone Mode)...\n")

    for product, expected in TEST_PRODUCTS:
        # 1. Gemini
        gemini_res = call_gemini(product)
        # 2. Llama 3.1
        llama_res = call_ollama(OLLAMA_MODELS["Llama3.1"], product)
        # 3. Qwen 3
        qwen_res = call_ollama(OLLAMA_MODELS["Qwen3"], product)

        results.append({
            "product": product,
            "expected": expected,
            "Gemini": gemini_res,
            "Llama3.1": llama_res,
            "Qwen3": qwen_res
        })
        print(f"Processed: {product}")

    # Print Table
    header = f"{'Product':<35} | {'Exp':<4} | {'Gemini':<8} | {'Llama':<8} | {'Qwen':<8}"
    print("\n" + header)
    print("-" * len(header))

    correct_counts = {"Gemini": 0, "Llama3.1": 0, "Qwen3": 0}

    for r in results:
        line = f"{r['product']:<35} | {r['expected']:<4} | {r['Gemini']:<8} | {r['Llama3.1']:<8} | {r['Qwen3']:<8}"
        print(line)

        if r['Gemini'] == r['expected']: correct_counts["Gemini"] += 1
        if r['Llama3.1'] == r['expected']: correct_counts["Llama3.1"] += 1
        if r['Qwen3'] == r['expected']: correct_counts["Qwen3"] += 1

    print("-" * len(header))
    print(f"Total Accuracy:  Gemini: {correct_counts['Gemini']}/{len(TEST_PRODUCTS)} | "
          f"Llama: {correct_counts['Llama3.1']}/{len(TEST_PRODUCTS)} | "
          f"Qwen: {correct_counts['Qwen3']}/{len(TEST_PRODUCTS)}")

if __name__ == "__main__":
    main()
