#!/usr/bin/env python3
"""
scripts/auto_review_items.py
────────────────────────────
CLI runner for AI-Powered Item Match Auto-Review & Curation (Method 2).

Usage:
  python scripts/auto_review_items.py [--limit 5000] [--dry-run]
"""

import argparse
import logging

from pipeline.gemini_item_reviewer import GeminiItemReviewer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("auto_review_items")

def main():
    parser = argparse.ArgumentParser(description="Auto-resolve pending item match reviews using Gemini AI & Attribute Guards.")
    parser.add_argument("--limit", type=int, default=10000, help="Maximum number of review rows to process")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without writing to the database")
    parser.add_argument("--use-rules-only", action="store_true", help="Use local attribute rules and heuristics (0 API calls)")
    args = parser.parse_args()

    log.info("Starting Auto-Reviewer (Limit: %d, Dry-run: %s, Rules-only: %s)...", args.limit, args.dry_run, args.use_rules_only)
    reviewer = GeminiItemReviewer()
    stats = reviewer.process_all_pending(limit=args.limit, dry_run=args.dry_run, use_rules_only=args.use_rules_only)

    print("\n" + "=" * 60)
    print("AUTO-REVIEW EXECUTION SUMMARY")
    print("=" * 60)
    print(f"Total Pending Processed : {stats['total_pending']}")
    print(f"Rule Auto-Approved      : {stats['rule_approved']}")
    print(f"Rule Auto-Split (Variant): {stats['rule_split']}")
    print(f"AI Auto-Approved        : {stats['ai_approved']}")
    print(f"AI Auto-Split           : {stats['ai_split']}")
    print(f"Skipped / Unresolved    : {stats['skipped']}")
    print("=" * 60)

if __name__ == "__main__":
    main()
