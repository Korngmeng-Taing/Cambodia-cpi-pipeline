import os
os.environ['OLLAMA_BASE_URL'] = 'http://localhost:11434'
import sys
sys.path.insert(0, ".")
from pipeline.ollama_client import OllamaClient
import json, time

SYSTEM_PROMPT = (
    "You are an expert COICOP 2018 classifier for Cambodia CPI.\n"
    "Classify each product into its most specific 5-digit COICOP code (format X.X.X).\n"
    "If unsure, return 99.9.9.\n"
    "Return ONLY a JSON array: [{\"product_name\":\"...\",\"coicop_code\":\"X.X.X\",\"confidence_score\":0.0-1.0,\"reasoning\":\"...\"}]\n"
    "\n"
    "Key mappings:\n"
    "- Rice, bread, noodles, pasta -> 01.1.1\n"
    "- Meat, pork, chicken, beef -> 01.1.2\n"
    "- Fish, seafood -> 01.1.3\n"
    "- Milk, cheese, eggs -> 01.1.4\n"
    "- Cooking oil -> 01.1.5\n"
    "- Fruit -> 01.1.6\n"
    "- Vegetables -> 01.1.7\n"
    "- Sugar, chocolate, candy -> 01.1.8\n"
    "- Sauce, seasoning -> 01.1.9\n"
    "- Coffee, tea -> 01.2.1\n"
    "- Soft drinks, juice, water -> 01.2.2\n"
    "- Beer, wine, spirits -> 02.x.x\n"
    "- Clothing, shoes -> 03.x.x\n"
    "- Housing rent -> 04.x.x\n"
    "- Furniture, utensils, cleaning -> 05.x.x\n"
    "- Medicine, pharma -> 06.x.x\n"
    "- Transport, fuel -> 07.x.x\n"
    "- Phone, internet -> 08.x.x\n"
    "- TV, audio, computer -> 09.x.x\n"
    "- Books, stationery -> 09.5.x\n"
    "- Restaurant, hotel -> 11.x.x\n"
    "- Shampoo, toothpaste, cosmetics -> 12.1.3\n"
    "- Backpack, suitcase -> 12.2.1\n"
)

PRODUCTS = [
    "Jasmine Rice 5kg",
    "Coca-Cola Can 330ml",
    "Pork Belly Fresh 1kg",
    "Angkor Beer 330ml",
    "Samsung Galaxy S24",
    "Colgate Toothpaste 100ml",
]

EXPECTED = {
    "Jasmine Rice 5kg": "01.1.1",
    "Coca-Cola Can 330ml": "01.2.2",
    "Pork Belly Fresh 1kg": "01.1.2",
    "Angkor Beer 330ml": "02.1.3",
    "Samsung Galaxy S24": "09.1.3",
    "Colgate Toothpaste 100ml": "12.1.3",
}

def main():
    client = OllamaClient(model="qwen3:8b")
    print(f"Qwen3:8b COICOP Classification Test")
    print(f"{'='*60}")

    correct = 0
    total_time = 0
    for product in PRODUCTS:
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
            exp = EXPECTED[product]
            match = code == exp
            if match:
                correct += 1
            mark = "OK" if match else "WRONG"
            print(f"  {product}")
            print(f"    -> {code} (expected {exp}) conf={conf} [{mark}] {elapsed:.1f}s")
        else:
            print(f"  {product} -> FAILED {elapsed:.1f}s")

    print(f"\n  SCORE: {correct}/{len(PRODUCTS)} | TOTAL: {total_time:.1f}s | AVG: {total_time/len(PRODUCTS):.1f}s")

if __name__ == "__main__":
    main()
