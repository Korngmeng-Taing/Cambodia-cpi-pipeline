"""
scripts/bootstrap_vector_embeddings.py
──────────────────────────────────────
Bootstrap and Pre-warm UN COICOP Reference Embeddings and Catalog Vectors.
Supports 3-Key API pooling for Google text-embedding-004 and local MiniLM.
"""

from __future__ import annotations

import logging
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pipeline.key_pool import get_key_pool
from pipeline.hybrid_embeddings_classifier import get_hybrid_classifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("bootstrap_vector_embeddings")


def main() -> int:
    log.info("Starting UN COICOP Reference Vector & Embedding Bootstrap...")
    pool = get_key_pool()
    log.info("Key Pool Status: %d active Gemini API key(s) detected.", pool.get_key_count())

    # 1. Initialize Hybrid Classifier and Precompute Reference Vectors
    classifier = get_hybrid_classifier()
    log.info("Successfully generated %d reference category vectors across 12 COICOP divisions.", len(classifier._ref_embeddings))

    # 2. Test sample classification across diverse retail domains
    test_products = [
        ("Angkor Premium Beer 330ml Can", "aeon", "02"),
        ("Fresh Salmon Fillet 500g", "delishop", "01"),
        ("Panadol Extra 500mg 24 Tablets", "communitypharma", "06"),
        ("Cetaphil Gentle Skin Cleanser 500ml", "communitypharma", "12"),
        ("Regular Gasoline 92 Octane", "new_gasoline", "07"),
        ("Samsung Galaxy S24 Ultra 256GB", "samnangshop", "08"),
        ("AEON Cotton Bath Towel White", "aeon", "05"),
    ]

    log.info("Running validation checks on sample Cambodian products...")
    passed = 0
    for name, store, expected_div in test_products:
        res = classifier.classify_product(name, store_slug=store)
        actual_div = res.get("coicop_division")
        method = res.get("classification_method")
        conf = res.get("confidence_score")
        
        status = "PASSED" if actual_div == expected_div else "MISMATCH"
        if status == "PASSED":
            passed += 1
        log.info("  [%s] '%s' (Store: %s) -> Division %s (Expected %s) [Method: %s, Conf: %.2f]",
                 status, name, store, actual_div, expected_div, method, conf)

    log.info("Bootstrap & Validation Complete: %d/%d test items verified.", passed, len(test_products))
    return 0 if passed == len(test_products) else 1


if __name__ == "__main__":
    sys.exit(main())
