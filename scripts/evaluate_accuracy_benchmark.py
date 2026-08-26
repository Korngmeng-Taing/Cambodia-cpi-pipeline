"""
scripts/evaluate_accuracy_benchmark.py
──────────────────────────────────────
End-to-End Accuracy Benchmark for:
1. Product Matching & Deduplication (with Spec Guards & Translation)
2. 12-Division UN COICOP Semantic Classification
"""

from __future__ import annotations

import os
import sys
import time
from collections import defaultdict

# Ensure UTF-8 output on Windows consoles
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pipeline.vector_item_matcher import VectorItemMatcher, is_spec_compatible, extract_specs
from pipeline.hybrid_embeddings_classifier import get_hybrid_classifier

# ============================================================================
# 1. GROUND TRUTH DATASETS
# ============================================================================

ITEM_MATCHING_GROUND_TRUTH = [
    # --- TRUE MATCHES (Should APPROVE_MATCH) ---
    {
        "candidate": "ស្រាបៀរអង្គរ កំប៉ុង 330ml",
        "canonical": "Angkor Premium Beer 330ml Can",
        "expected": "APPROVE_MATCH",
        "category": "Khmer <-> English Translation"
    },
    {
        "candidate": "Coke Original Taste 330ml Can",
        "canonical": "Coca-Cola 330ml Can",
        "expected": "APPROVE_MATCH",
        "category": "Brand Synonym"
    },
    {
        "candidate": "Fresh Atlantic Salmon Fillet 500g",
        "canonical": "Salmon Fillet Fresh 500g",
        "expected": "APPROVE_MATCH",
        "category": "Word Order Variation"
    },
    {
        "candidate": "Panadol Extra 500mg 24 Tablets",
        "canonical": "Panadol Extra Tablets 500mg 24s",
        "expected": "APPROVE_MATCH",
        "category": "Pharmacy Formulation"
    },
    {
        "candidate": "iPhone 15 Pro Max 256GB Natural Titanium",
        "canonical": "Apple iPhone 15 Pro Max 256GB Titanium",
        "expected": "APPROVE_MATCH",
        "category": "Electronics Match"
    },
    {
        "candidate": "Cetaphil Gentle Skin Cleanser 500ml",
        "canonical": "Cetaphil Cleanser Gentle Skin 500ml",
        "expected": "APPROVE_MATCH",
        "category": "Personal Care Match"
    },

    # --- TRUE NON-MATCHES / CONFLICTS (Should SPLIT_NEW) ---
    {
        "candidate": "Samsung Galaxy S24 128GB Black",
        "canonical": "Samsung Galaxy S24 256GB Black",
        "expected": "SPLIT_NEW",
        "category": "Storage Spec Conflict (128GB vs 256GB)"
    },
    {
        "candidate": "Coca-Cola 330ml Single Can",
        "canonical": "Coca-Cola 330ml Pack of 6",
        "expected": "SPLIT_NEW",
        "category": "Pack Size Conflict (1 vs 6)"
    },
    {
        "candidate": "Angkor Beer 330ml x24 Cans",
        "canonical": "Angkor Beer 330ml Single Can",
        "expected": "SPLIT_NEW",
        "category": "Case vs Single Conflict"
    },
    {
        "candidate": "Fresh Milk 1000ml (1L)",
        "canonical": "Fresh Milk 330ml",
        "expected": "SPLIT_NEW",
        "category": "Volume Conflict (1000ml vs 330ml)"
    },
    {
        "candidate": "Coca-Cola Zero Sugar 330ml",
        "canonical": "Coca-Cola Original Taste 330ml",
        "expected": "SPLIT_NEW",
        "category": "Diet vs Original Flavor Variant"
    }
]

COICOP_CLASSIFICATION_GROUND_TRUTH = [
    # Division 01: Food
    {"name": "AEON Organic Jasmine Rice 5kg", "store": "aeon", "division": "01", "desc": "Rice"},
    {"name": "Fresh Australian Beef Tenderloin 500g", "store": "delishop", "division": "01", "desc": "Beef Meat"},
    {"name": "ត្រីសាម៉ុងស្រស់ 500g", "store": "delishop", "division": "01", "desc": "Fresh Salmon in Khmer"},
    {"name": "Nestle Full Cream Fresh Milk 1L", "store": "aeon", "division": "01", "desc": "Dairy Milk"},
    {"name": "Indomie Mi Goreng Instant Noodles 85g", "store": "aeon", "division": "01", "desc": "Instant Noodles"},

    # Division 02: Alcohol & Tobacco
    {"name": "Angkor Premium Beer 330ml Can", "store": "aeon", "division": "02", "desc": "Local Beer"},
    {"name": "Johnnie Walker Black Label Scotch Whisky 700ml", "store": "delishop", "division": "02", "desc": "Whisky"},
    {"name": "Chateau Margaux Bordeaux Red Wine 750ml", "store": "delishop", "division": "02", "desc": "Red Wine"},

    # Division 03: Clothing
    {"name": "Men Cotton Crewneck T-Shirt Navy M", "store": "aeon3", "division": "03", "desc": "Apparel T-Shirt"},
    {"name": "Women Denim Skinny Jeans Blue", "store": "l192", "division": "03", "desc": "Denim Jeans"},
    {"name": "Nike Air Max Running Shoes Black 42", "store": "aeon3", "division": "03", "desc": "Footwear"},

    # Division 04: Housing & Utilities
    {"name": "Monthly Apartment Rent BKK1 2 Bedrooms", "store": "realestate", "division": "04", "desc": "Apartment Rent"},
    {"name": "LPG Cooking Gas Refill Cylinder 15kg", "store": "khmer24", "division": "04", "desc": "Cooking Gas"},

    # Division 05: Furnishings & Cleaning
    {"name": "AEON Cotton Bath Towel 70x140cm White", "store": "aeon", "division": "05", "desc": "Bath Towel"},
    {"name": "Attack Concentrated Laundry Detergent Liquid 1.4kg", "store": "aeon", "division": "05", "desc": "Detergent"},
    {"name": "Non-Stick Frying Pan 28cm Induction", "store": "l192", "division": "05", "desc": "Cookware"},

    # Division 06: Health & Pharmacy
    {"name": "Panadol Extra 500mg Paracetamol 24 Tablets", "store": "communitypharma", "division": "06", "desc": "Painkiller Medicine"},
    {"name": "Tiger Balm Red Ointment 19g", "store": "communitypharma", "division": "06", "desc": "Medical Balm"},
    {"name": "Omron Digital Blood Pressure Monitor HEM-7120", "store": "communitypharma", "division": "06", "desc": "Medical Device"},

    # Division 07: Transport & Fuel
    {"name": "Super 95 Octane Gasoline per Liter", "store": "new_gasoline", "division": "07", "desc": "Automotive Fuel"},
    {"name": "Phnom Penh to Siem Reap Luxury Bus Ticket", "store": "redbus", "division": "07", "desc": "Intercity Transit"},

    # Division 08: Telecom & Phones
    {"name": "Smart VIP Data Unlimited Monthly 4G Plan", "store": "smart", "division": "08", "desc": "Mobile Data Plan"},
    {"name": "Apple iPhone 15 Pro Max 256GB", "store": "samnangshop", "division": "08", "desc": "Smartphone"},

    # Division 09: Recreation & Electronics
    {"name": "Sony Wireless Noise Cancelling Headphones WH-1000XM5", "store": "aeon", "division": "09", "desc": "Audio Electronics"},
    {"name": "LEGO City Police Station Building Set", "store": "aeon", "division": "09", "desc": "Toys"},

    # Division 11: Restaurants & Hotels
    {"name": "Sokha Phnom Penh Hotel Deluxe River View 1 Night", "store": "sokhahotel", "division": "11", "desc": "Hotel Room"},
    {"name": "Bayon Restaurant Khmer Curry Chicken Set Meal", "store": "bayonbkk", "division": "11", "desc": "Restaurant Meal"},

    # Division 12: Personal Care & Hygiene (Key test for Community Pharma & AEON)
    {"name": "Cetaphil Gentle Skin Cleanser 500ml", "store": "communitypharma", "division": "12", "desc": "Skincare Cleanser"},
    {"name": "Head & Shoulders Anti-Dandruff Shampoo 450ml", "store": "communitypharma", "division": "12", "desc": "Hair Shampoo"},
    {"name": "Colgate Total 12 Professional Clean Toothpaste 150g", "store": "aeon", "division": "12", "desc": "Oral Care Toothpaste"},
    {"name": "Biore UV Aqua Rich Watery Essence Sunscreen SPF50+ 50g", "store": "communitypharma", "division": "12", "desc": "Sunscreen Lotion"},
    {"name": "Pampers Baby Dry Diapers Size L 44 Pants", "store": "aeon", "division": "12", "desc": "Baby Care Diapers"}
]


def evaluate_item_matching() -> dict:
    print("\n" + "="*80)
    print(" 1. BENCHMARK: PRODUCT MATCHING & SPEC GUARD ACCURACY")
    print("="*80)
    matcher = VectorItemMatcher()

    correct = 0
    total = len(ITEM_MATCHING_GROUND_TRUTH)
    results = []

    for item in ITEM_MATCHING_GROUND_TRUTH:
        cand = item["candidate"]
        base = item["canonical"]
        expected = item["expected"]
        cat = item["category"]

        catalog_mock = [{"item_id": "uuid-canon-1", "canonical_name": base, "vector": matcher.embed_text(base)}]
        res = matcher.match_candidate(cand, catalog_mock)
        actual = res["decision"]

        is_correct = (actual == expected)
        if is_correct:
            correct += 1

        results.append({
            "candidate": cand,
            "canonical": base,
            "category": cat,
            "expected": expected,
            "actual": actual,
            "conf": res.get("confidence", 1.0),
            "status": "PASS" if is_correct else "FAIL"
        })

    print(f"{'Status':<6} | {'Expected':<13} | {'Actual':<13} | {'Confidence':<10} | {'Test Category / Pair'}")
    print("-" * 80)
    for r in results:
        print(f"[{r['status']}]  | {r['expected']:<13} | {r['actual']:<13} | {r['conf']:<10.3f} | {r['category']}")

    accuracy = (correct / total) * 100
    print("-" * 80)
    print(f"Item Matching Overall Accuracy: {correct}/{total} ({accuracy:.1f}%)\n")
    return {"accuracy": accuracy, "correct": correct, "total": total}


def evaluate_coicop_classification() -> dict:
    print("\n" + "="*80)
    print(" 2. BENCHMARK: 12-DIVISION COICOP CLASSIFICATION ACCURACY")
    print("="*80)
    classifier = get_hybrid_classifier()

    correct = 0
    total = len(COICOP_CLASSIFICATION_GROUND_TRUTH)
    per_div_stats = defaultdict(lambda: {"total": 0, "correct": 0})
    results = []

    for item in COICOP_CLASSIFICATION_GROUND_TRUTH:
        name = item["name"]
        store = item["store"]
        expected_div = item["division"]
        desc = item["desc"]

        res = classifier.classify_product(name, store_slug=store)
        actual_div = res.get("coicop_division")
        conf = res.get("confidence_score", 0.0)
        method = res.get("classification_method", "unknown")

        is_correct = (actual_div == expected_div)
        if is_correct:
            correct += 1
            per_div_stats[expected_div]["correct"] += 1
        per_div_stats[expected_div]["total"] += 1

        results.append({
            "name": name,
            "store": store,
            "desc": desc,
            "expected": expected_div,
            "actual": actual_div,
            "conf": conf,
            "method": method,
            "status": "PASS" if is_correct else "FAIL"
        })

    print(f"{'Status':<6} | {'Store':<15} | {'Exp':<4} | {'Act':<4} | {'Conf':<6} | {'Method':<16} | {'Product Name / Description'}")
    print("-" * 95)
    for r in results:
        clean_name = r['name'].encode('ascii', 'backslashreplace').decode('ascii')
        print(f"[{r['status']}]  | {r['store']:<15} | {r['expected']:<4} | {r['actual']:<4} | {r['conf']:<6.2f} | {r['method']:<16} | {clean_name[:30]} ({r['desc']})")

    accuracy = (correct / total) * 100
    print("-" * 95)
    print(f"COICOP Classification Overall Accuracy: {correct}/{total} ({accuracy:.1f}%)")

    print("\nPer-Division Accuracy Summary:")
    for div in sorted(per_div_stats.keys()):
        d = per_div_stats[div]
        pct = (d["correct"] / d["total"]) * 100
        print(f"  Division {div}: {d['correct']}/{d['total']} ({pct:.1f}%)")

    return {"accuracy": accuracy, "correct": correct, "total": total, "per_div": per_div_stats}


def main():
    start_t = time.time()
    print("Starting Comprehensive Silver Layer Accuracy Evaluation...")

    match_res = evaluate_item_matching()
    class_res = evaluate_coicop_classification()

    elapsed = time.time() - start_t
    print("\n" + "="*80)
    print(" EXECUTIVE ACCURACY SCORECARD")
    print("="*80)
    print(f" 1. Product Matching & Spec Guard Accuracy : {match_res['accuracy']:.1f}% ({match_res['correct']}/{match_res['total']})")
    print(f" 2. 12-Division COICOP Semantic Accuracy    : {class_res['accuracy']:.1f}% ({class_res['correct']}/{class_res['total']})")
    print(f" Total Benchmark Runtime                   : {elapsed:.2f} seconds")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
