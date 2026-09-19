"""
scripts/automated_rule_suggester.py
─────────────────────────────────────
Self-Learning Rule Engine.
Analyzes manual corrections in `silver.coicop_override_manual`, uses an LLM to
identify recurring patterns, and proposes new Regex rules for `dbt_seeds.coicop_text_rules`.
"""

from __future__ import annotations

import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.config import get_db_connection
from pipeline.key_pool import GeminiKeyPool

try:
    from google import genai
    from google.genai import types as genai_types
    HAS_GENAI = True
except ImportError:
    genai = None
    genai_types = None
    HAS_GENAI = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("rule_suggester")

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

def analyze_manual_fixes(conn):
    """Fetch recently manually corrected items."""
    cur = conn.cursor()
    cur.execute("""
        SELECT canonical_name, coicop_division, coicop_code
        FROM silver.manual_item_corrections
        ORDER BY corrected_at DESC
        LIMIT 200;
    """)
    return cur.fetchall()

def propose_rules(fixes: list[tuple[str, str, str]]):
    """Use Gemini Flash to find patterns in manual fixes and suggest regex rules."""
    if not fixes:
        return []

    pool = GeminiKeyPool()
    if not pool.has_keys or not HAS_GENAI:
        log.warning("No Gemini API keys or google-genai library available.")
        return []

    fixes_text = "\n".join([f"Name: {n} -> Div: {d}, Code: {c}" for n, d, c in fixes])

    sys_prompt = (
        "You are a COICOP Rule Engineer. Analyze these manual classification fixes "
        "and identify recurring patterns. Propose a set of Regular Expressions (regex) "
        "that would have correctly classified these items automatically.\n\n"
        "Return JSON as a list of objects: [{\"pattern\": \"...\", \"division\": \"XX\", \"code\": \"XX.X.X\", \"reason\": \"...\"}]"
    )

    prompt = f"Manual Fixes:\n{fixes_text}\n\nPropose deterministic regex rules:"

    key_handle = pool.get_client()
    try:
        client = key_handle.client
        config = genai_types.GenerateContentConfig(
            system_instruction=sys_prompt,
            response_mime_type="application/json",
            temperature=0.1,
        )
        response = client.models.generate_content(
            model=DEFAULT_MODEL,
            contents=prompt,
            config=config,
        )
        text = response.text.strip()
        result = json.loads(text)
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "rules" in result:
            return result["rules"]
        if isinstance(result, dict):
            return result
        return []
    except Exception as e:
        log.error("Error generating rule suggestions via Gemini: %s", e)
        return []

def run():
    conn = get_db_connection()

    try:
        fixes = analyze_manual_fixes(conn)
        if not fixes:
            log.info("No manual fixes found to analyze.")
            return

        log.info("Analyzing %d manual fixes for patterns...", len(fixes))
        suggestions = propose_rules(fixes)

        if not suggestions:
            log.info("No clear patterns found to suggest rules.")
            return

        log.info("=" * 70)
        log.info("SUGGESTED DETERMINISTIC RULES:")
        log.info("-" * 70)
        for i, rule in enumerate(suggestions):
            print(f"Rule #{i+1}:")
            print(f"  Pattern: {rule.get('pattern')}")
            print(f"  Div: {rule.get('division')} | Code: {rule.get('code')}")
            print(f"  Reason: {rule.get('reason')}")
            print("-" * 30)
        log.info("=" * 70)
        log.info("To apply these, add them to dbt/seeds/coicop_text_rules.csv")

    except Exception as e:
        log.exception("Rule suggestion failed: %s", e)
    finally:
        conn.close()

if __name__ == "__main__":
    run()
