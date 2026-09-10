import os
os.environ['OLLAMA_BASE_URL'] = 'http://localhost:11434'
os.environ['OLLAMA_MODEL'] = 'qwen3:8b'
import sys
sys.stdout.reconfigure(encoding='utf-8')
import sys
sys.path.insert(0, ".")
from pipeline.ollama_client import OllamaClient
import json, time

# Use the same system prompt as gemini_coicop_classifier.py but adapted for Ollama
SYSTEM_PROMPT = (
    "You are an expert statistical classifier for the UN COICOP 2018 taxonomy "
    "(Classification of Individual Consumption According to Purpose).\n"
    "I will give you product names from Cambodia. Classify each into its most specific 5-digit COICOP code.\n"
    "If unsure, return '99.9.9'.\n"
    "Include 'product_name', 'coicop_code', 'confidence_score' (0.0-1.0), and 'reasoning'.\n\n"
    "Critical rules:\n"
    "- Retail supermarket food is ALWAYS Division 01 (sandwiches, pizza, ready meals are FOOD, not Division 11)\n"
    "- Division 11 is ONLY for dine-in restaurant services\n"
    "- 'Coffee Filter', 'Tea Strainer' -> 05.5.1, NOT 01.2.1\n"
    "- 'Slippers', 'Sandals' -> 03.2.1 (Footwear)\n"
    "- Cooking Wine, Mirin -> 01.1.9, NOT 02.1.2\n"
    "- 0.0% alcohol-free beer -> 01.2.2, real beer -> 02.2.1\n"
    "- Sunscreen, shampoo, toothpaste -> 12.1.3\n"
    "- Smartphones, tablets -> 08.2.0\n"
    "- Books, notebooks -> 09.5.x\n"
    "- Plush toys, board games -> 09.3.1\n"
    "- Cleaning products -> 05.6.1\n"
    "- OTC medicines -> 06.1.2\n\n"
    "Common codes: 01.1.1 Bread/cereals, 01.1.2 Meat, 01.1.3 Fish, 01.1.4 Milk/cheese/eggs, "
    "01.1.5 Oils, 01.1.6 Fruit, 01.1.7 Vegetables, 01.1.8 Sugar/confectionery, 01.1.9 Food n.e.c., "
    "01.2.1 Coffee/tea, 01.2.2 Soft drinks, 02.1.1 Spirits, 02.1.2 Wine, 02.2.1 Beer, "
    "03.1.x Garments, 03.2.1 Footwear, 04.1.1 Housing rent, 05.x.x Furnishings, "
    "06.x.x Health, 07.x.x Transport, 08.2.0 Phone equipment, 08.3.0 Internet, "
    "09.1.1 Audio/visual, 09.1.3 IT equipment, 09.3.1 Games/toys, 09.5.1 Books, "
    "11.1.1 Restaurants, 11.2.0 Accommodation, 12.1.3 Personal care, 12.2.1 Travel goods\n\n"
    "Return ONLY a JSON array: [{\"product_name\":\"...\",\"coicop_code\":\"X.X.X\",\"confidence_score\":0.0-1.0,\"reasoning\":\"...\"}]"
)

TEST_PRODUCTS = [
    "Jasmine Rice 5kg",
    "Coca-Cola Can 330ml",
    "Pork Belly Fresh 1kg",
    "Angkor Beer 330ml",
    "Samsung Galaxy S24",
    "Colgate Toothpaste 100ml",
    "Fresh Salmon Fillet 200g",
    "Men Cotton T-Shirt",
    "TV Coffee Filter 40",
    "Panadol Extra 500mg 10s",
    "Bus Ticket Phnom Penh-Siem Reap",
    "Regular Gasoline 1L",
    "Sony Wireless Headphones",
    "Pedigree Dog Food Beef 1.5kg",
    "5 Second Rules Junior Board Game",
    "EXERCISE BOOK A4",
    "Wire Cutters Pliers 6 Inches",
    "Head & Shoulders Shampoo 450ml",
    "Sunplay Skin Aqua SPF50",
    "Foldable Travel Backpack 20L",
]

EXPECTED = {
    "Jasmine Rice 5kg": "01.1.1",
    "Coca-Cola Can 330ml": "01.2.2",
    "Pork Belly Fresh 1kg": "01.1.2",
    "Angkor Beer 330ml": "02.1.3",
    "Samsung Galaxy S24": "08.2.0",
    "Colgate Toothpaste 100ml": "12.1.3",
    "Fresh Salmon Fillet 200g": "01.1.3",
    "Men Cotton T-Shirt": "03.1.1",
    "TV Coffee Filter 40": "05.5.1",
    "Panadol Extra 500mg 10s": "06.1.2",
    "Bus Ticket Phnom Penh-Siem Reap": "07.1.2",
    "Regular Gasoline 1L": "07.2.2",
    "Sony Wireless Headphones": "09.1.1",
    "Pedigree Dog Food Beef 1.5kg": "09.3.4",
    "5 Second Rules Junior Board Game": "09.3.1",
    "EXERCISE BOOK A4": "09.5.4",
    "Wire Cutters Pliers 6 Inches": "05.5.2",
    "Head & Shoulders Shampoo 450ml": "12.1.3",
    "Sunplay Skin Aqua SPF50": "12.1.3",
    "Foldable Travel Backpack 20L": "12.2.1",
}

def main():
    client = OllamaClient(model="qwen3:8b")
    print("=" * 70)
    print("  Qwen3:8b COICOP Classification Test (Full System Prompt)")
    print("=" * 70)

    correct = 0
    total_time = 0
    results = []

    for product in TEST_PRODUCTS:
        t0 = time.time()
        result = client.generate(
            prompt="Classify this product: " + product,
            system_prompt=SYSTEM_PROMPT,
            format_json=True,
        )
        elapsed = time.time() - t0
        total_time += elapsed
        if result:
            items = result if isinstance(result, list) else [result]
            item = items[0] if items else {}
            code = item.get("coicop_code", "?")
            conf = item.get("confidence_score", "?")
            reasoning = item.get("reasoning", "")
            exp = EXPECTED[product]
            match = code == exp
            if match:
                correct += 1
            mark = "OK" if match else "WRONG"
            results.append((product, code, exp, mark, conf, elapsed))
            print(f"  [{mark}] {product}")
            print(f"       -> {code} (expected {exp}) conf={conf} {elapsed:.1f}s")
            if not match:
                print(f"       Reasoning: {reasoning[:80]}")
        else:
            results.append((product, "?", EXPECTED[product], "FAIL", 0, elapsed))
            print(f"  [FAIL] {product} -> No response {elapsed:.1f}s")

    # Summary
    print(f"\n{'='*70}")
    print(f"  SUMMARY: {correct}/{len(TEST_PRODUCTS)} correct")
    print(f"  Accuracy: {correct/len(TEST_PRODUCTS)*100:.1f}%")
    print(f"  Total time: {total_time:.1f}s | Avg: {total_time/len(TEST_PRODUCTS):.1f}s")
    print(f"{'='*70}")

    # Per-division breakdown
    div_correct = {}
    div_total = {}
    for product, code, exp, mark, conf, elapsed in results:
        exp_div = exp.split(".")[0]
        div_total[exp_div] = div_total.get(exp_div, 0) + 1
        if mark == "OK":
            div_correct[exp_div] = div_correct.get(exp_div, 0) + 1

    print("\nPer-Division Accuracy:")
    for div in sorted(div_total.keys()):
        c = div_correct.get(div, 0)
        t = div_total[div]
        print(f"  Division {div}: {c}/{t} ({c/t*100:.1f}%)")

if __name__ == "__main__":
    main()
