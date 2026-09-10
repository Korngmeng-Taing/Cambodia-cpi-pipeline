import logging
from pipeline.hierarchical_classifier import HierarchicalCOICOPClassifier

logging.basicConfig(level=logging.WARNING) # Keep log quiet for the interactive tool
logger = logging.getLogger(__name__)

def main():
    print("=====================================================")
    print("   COICOP CLASSIFIER QA TESTING TOOL (Debug Mode)     ")
    print("=====================================================\n")
    
    try:
        classifier = HierarchicalCOICOPClassifier(hierarchy_path="coicop_hierarchy.json")
        print("✅ Classifier initialized successfully.\n")
    except Exception as e:
        print(f"❌ Initialization failed: {e}")
        return

    print("Enter a product name to test (or 'exit' to quit).")
    print("You can also use format 'Product Name | store_slug' to test specific stores.")
    
    while True:
        user_input = input("\nProduct Name > ").strip()
        if not user_input:
            continue
        if user_input.lower() in ('exit', 'quit'):
            break
            
        # Handle optional store_slug
        product_name = user_input
        store_slug = "generic_store"
        if "|" in user_input:
            parts = user_input.split("|")
            product_name = parts[0].strip()
            store_slug = parts[1].strip()

        print(f"\n🔍 Classifying: '{product_name}' (Store: {store_slug})")
        print("-" * 40)
        
        try:
            # We use a dummy item_id for testing since we don't want to pollute the cache
            result, path = classifier.classify_debug(item_id="TEST_ID", product_name=product_name, store_slug=store_slug)
            
            for step in path:
                print(f"  {step}")
            
            print("-" * 40)
            print(f"🏁 RESULT: {result['code']}")
            print(f"🛠️  METHOD: {result['method']}")
            print(f"🎯 CONFIDENCE: {result['confidence']:.2f}")
            
        except Exception as e:
            print(f"❌ Error during classification: {e}")

    print("\nExiting QA Tool. Goodbye!")

if __name__ == "__main__":
    main()
