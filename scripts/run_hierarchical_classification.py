import argparse
import logging
import sys
from pathlib import Path

# Ensure repo root is in sys.path
repo_root = str(Path(__file__).resolve().parent.parent)
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from pipeline.gemini_coicop_classifier import GeminiCOICOPClassifier

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Gemini COICOP Classifier")
    parser.add_argument("--ds", type=str, default=None, help="Scrape date to prioritize")
    parser.add_argument("--limit", type=int, default=0, help="Maximum items to classify (0 = all items of the date)")
    args = parser.parse_args()

    logger.info("Initializing Gemini COICOP Classifier (ds: %s, limit: %s)...", args.ds, "ALL" if args.limit == 0 else args.limit)
    classifier = GeminiCOICOPClassifier()
    stats = classifier.classify_unclassified_canonical_items(limit=args.limit, scrape_date=args.ds)
    logger.info("Gemini COICOP batch classification finished: %s", stats)


if __name__ == "__main__":
    main()
