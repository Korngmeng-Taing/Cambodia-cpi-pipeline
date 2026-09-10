
import sys, json, time
sys.path.insert(0, ".")
from pipeline.ollama_client import OllamaClient

product = "Jasmine Rice 5kg"
system_prompt = "You classify products for Cambodia CPI using COICOP 2018. Return a JSON array with objects: product_name, coicop_code (format X.X.X), coicop_description, confidence_score (0.0-1.0), reasoning."

print(f"Testing Qwen3:8B with: {product}")
client = OllamaClient(model="qwen3:8b")
t0 = time.time()
result = client.generate(
    prompt="Classify this product: " + product,
    system_prompt=system_prompt,
    format_json=True,
)
elapsed = time.time() - t0
print(f"Result: {result}")
print(f"Time: {elapsed:.1f}s")
