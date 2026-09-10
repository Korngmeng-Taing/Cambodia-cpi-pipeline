import sys, json, time
sys.path.insert(0, ".")
from pipeline.ollama_client import OllamaClient

test_products = [
    "Jasmine Rice 5kg",
    "Coca-Cola Can 330ml",
    "Pork Belly Fresh 1kg",
    "Angkor Beer 330ml",
    "Campbells Chicken Noodle Soup",
    "Colgate Toothpaste 100ml",
    "Samsung Galaxy S24",
]

system_prompt = (
    "You classify products for Cambodia CPI using COICOP 2018. "
    "Return a JSON array with objects: product_name, coicop_code (format X.X.X), "
    "coicop_description, confidence_score (0.0-1.0), reasoning.\n\n"
    "COICOP Codes:\n"
    "01.1.1 - Bread and cereals\n"
    "01.1.2 - Meat\n"
    "01.1.3 - Fish and seafood\n"
    "01.1.4 - Milk, cheese and eggs\n"
    "01.1.5 - Oils and fats\n"
    "01.1.6 - Fruit\n"
    "01.1.7 - Vegetables\n"
    "01.1.8 - Sugar, jam, honey, chocolate, snacks\n"
    "01.1.9 - Food products n.e.c.\n"
    "01.2.1 - Coffee, tea and cocoa\n"
    "01.2.2 - Mineral waters, soft drinks, juices\n"
    "02.1.1 - Spirits and liqueurs\n"
    "02.1.3 - Beer\n"
    "02.2.0 - Tobacco\n"
    "05.5.1 - Glassware, tableware, utensils\n"
    "06.1.1 - Pharmaceutical products\n"
    "07.2.2 - Fuels and lubricants\n"
    "08.3.0 - Telephone and internet services\n"
    "09.1.3 - Information processing equipment\n"
    "12.1.3 - Personal care products\n\n"
    "Return ONLY the JSON array."
)

expected = {
    "Jasmine Rice 5kg": "01.1.1",
    "Coca-Cola Can 330ml": "01.2.2",
    "Pork Belly Fresh 1kg": "01.1.2",
    "Angkor Beer 330ml": "02.1.3",
    "Campbells Chicken Noodle Soup": "01.1.1",
    "Colgate Toothpaste 100ml": "12.1.3",
    "Samsung Galaxy S24": "09.1.3",
}

for model_name in ["llama3.1", "qwen3:8b"]:
    print(f"\n{'='*60}")
    print(f"  MODEL: {model_name}")
    print(f"{'='*60}")
    client = OllamaClient(model=model_name)
    correct = 0
    total_time = 0
    for product in test_products:
        t0 = time.time()
        result = client.generate(
            prompt="Classify this product: " + product,
            system_prompt=system_prompt,
            format_json=True,
        )
        elapsed = time.time() - t0
        total_time += elapsed
        if result:
            items = result if isinstance(result, list) else [result]
            item = items[0]
            code = item.get("coicop_code", "?")
            exp = expected[product]
            match = code == exp
            if match:
                correct += 1
            mark = "OK" if match else "WRONG"
            print(f"  {product}")
            print(f"    {code} (expected {exp}) [{mark}] {elapsed:.1f}s")
        else:
            print(f"  {product} -> FAILED {elapsed:.1f}s")
    print(f"\n  SCORE: {correct}/{len(test_products)} | TIME: {total_time:.1f}s")
