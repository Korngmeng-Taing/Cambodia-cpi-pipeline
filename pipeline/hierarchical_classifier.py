import json
import re
from pipeline.ollama_client import OllamaClient
import logging
from typing import Tuple, Optional, Dict, Any
from pipeline.config import get_db_connection
from pipeline.key_pool import GeminiKeyPool
from pipeline.vector_item_matcher import VectorItemMatcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HierarchicalCOICOPClassifier:
    def __init__(self, hierarchy_path: str, ollama_url: str = "http://localhost:11434",
                 llama_model: str = "llama3.1:latest", gemini_model: str = "gemini-3.1-flash-lite"):
        self.hierarchy = self._load_hierarchy(hierarchy_path)
        self.ollama_client = OllamaClient(model=llama_model, base_url=ollama_url)
        self.gemini_model = gemini_model
        self.gemini_pool = GeminiKeyPool()
        self.vector_matcher = VectorItemMatcher()

    def _load_hierarchy(self, path: str) -> Dict:
        with open(path, 'r') as f:
            return json.load(f)

    def _call_llm(self, prompt: str, model_type: str = "llama") -> str:
        """Calls the LLM and returns the extracted 2 or 5 digit code."""
        if model_type == "llama":
            try:
                # Use OllamaClient for structured chat-based interaction
                res = self.ollama_client.generate(prompt, format_json=False)
                if res:
                    # If the client returned a dict, we might need to extract the text
                    text = res if isinstance(res, str) else str(res)
                    match = re.search(r'\d{2}(\.\d{1,2}){0,3}', text)
                    return match.group(0) if match else "ERR"
                return "ERR"
            except Exception as e:
                logger.error(f"Ollama error: {e}")
                return self._call_gemini_fallback(prompt)
        else:
            return self._call_gemini_fallback(prompt)

    def _call_gemini_fallback(self, prompt: str) -> str:
        """Fallback to Gemini if local LLM fails or is requested."""
        try:
            key = self.gemini_pool.get_next_key()
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={key}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
            text = data['candidates'][0]['content']['parts'][0]['text'].strip()
            match = re.search(r'\d{2}(\.\d{1,2}){0,3}', text)
            return match.group(0) if match else "ERR"
        except Exception as e:
            logger.error(f"Gemini fallback error: {e}")
            return "ERR"

    def _get_decision(self, product_name: str, options_map: Dict) -> Optional[str]:
        """Generic prompt to pick a code from a provided map of options. Driven by Llama 3.1."""
        options = []
        for code, info in options_map.items():
            name = info["name"] if isinstance(info, dict) else info
            options.append(f"{code}: {name}")

        options_str = "\n".join(options)
        prompt = f"""You are a COICOP classification expert.
Classify the product: '{product_name}'
Choose the most accurate code from this list:
{options_str}

CRITICAL RULES:
- PET FOOD & PET TREATS: Dog food, cat food, bird seed, pet treats -> 09.3.4 (Pets and related products), NEVER 01 (Human Food).
- RETAIL FOOD: Packaged/ready meals in supermarkets are Division 01, NOT 11.
- PERSONAL CARE: Skincare, shampoo, makeup -> 12.1.3.

Return ONLY the code. No explanation. No punctuation. Example: 01.1.1"""

        # Llama 3.1 acts as the Driver for high-volume decision making
        result = self._call_llm(prompt, model_type="llama")
        return result if result != "ERR" else None

    def classify(self, item_id: str, product_name: str, store_slug: str) -> Tuple[str, str, float]:
        """The complete Incremental Hybrid Ladder workflow."""
        # Call debug version and return only the final result
        res, _ = self.classify_debug(item_id, product_name, store_slug)
        return res['code'], res['method'], res['confidence']

    def classify_debug(self, item_id: str, product_name: str, store_slug: str) -> Tuple[Dict, list]:
        """Detailed version of classify that returns the decision path."""
        path = []

        # 1. Cache Shortcut
        path.append("Checking Cache...")
        cached = self._check_cache(item_id)
        if cached:
            path.append(f"✅ Found in cache: {cached['code']}")
            return {'code': cached['code'], 'method': 'cache', 'confidence': cached['confidence']}, path

        # 2. Deterministic Rules (Purity & Traps)
        path.append("Checking Deterministic Rules (Purity/Traps)...")
        rule_res = self._check_deterministic_rules(product_name, store_slug)
        if rule_res:
            code, method = rule_res
            path.append(f"✅ Matched {method}: {code}")
            return {'code': code, 'method': method, 'confidence': 1.0}, path

        # 3. Vector Fast-Lane (Gold Library)
        path.append("Checking Vector Fast-Lane (Gold Library)...")
        vector_res = self._check_vector_fastlane(product_name)
        if vector_res:
            code, confidence = vector_res
            path.append(f"✅ Semantic match in Gold Table: {code} (Sim: {confidence:.2f})")
            return {'code': code, 'method': "vector_fastlane", 'confidence': confidence}, path

        # 4. Hierarchical AI Drill-Down
        path.append("Starting Hierarchical AI Drill-Down...")
        ai_res = self._run_hierarchical_ai(product_name)
        if ai_res:
            code, confidence = ai_res
            path.append(f"🤖 AI Proposed Code: {code}")

            # 5. Self-Correction Guard
            path.append("Requesting Gemini Judge verification...")
            if self._verify_decision(product_name, code):
                path.append(f"✅ Gemini Judge approved: {code}")
                return {'code': code, 'method': "hierarchical_ai", 'confidence': confidence}, path
            else:
                path.append(f"❌ Gemini Judge rejected: {code}")
                logger.info(f"AI self-corrected: {product_name} was rejected.")

        # Final Fallback
        path.append("No confident classification found. Falling back to UNCLASSIFIED.")
        return {'code': "UNCLASSIFIED", 'method': "fallback", 'confidence': 0.0}, path

    def _check_cache(self, item_id: str) -> Optional[Dict]:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT coicop_code, coicop_method, confidence FROM silver.classification_cache WHERE item_id = %s", (item_id,))
            row = cur.fetchone()
            if row:
                return {'code': row[0], 'method': row[1], 'confidence': float(row[2])}
        return None

    def _check_deterministic_rules(self, product_name: str, store_slug: str) -> Optional[Tuple[str, str]]:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Check Store Purity
            cur.execute("SELECT lpad(coicop_division::text, 2, '0') || '.0.0' FROM silver.store_purity WHERE store_slug = %s", (store_slug,))
            res = cur.fetchone()
            if res: return res[0], "store_purity"

            # Check Critical Traps (Assuming traps are in a table or loaded in memory)
            # For now, we'll assume they are in a table silver.coicop_critical_traps
            cur.execute("""
                SELECT coicop_code FROM silver.coicop_critical_traps
                WHERE position(upper(pattern) in upper(%s)) > 0
                OR %s ~* pattern
            """, (product_name, product_name))
            res = cur.fetchone()
            if res: return res[0], "critical_trap"

        return None

    def _check_vector_fastlane(self, product_name: str) -> Optional[Tuple[str, float]]:
        """Check for a semantic match in the Gold Standard table."""
        return self.vector_matcher.find_closest_match(product_name)

    def _run_hierarchical_ai(self, product_name: str) -> Optional[Tuple[str, float]]:
        # Step 1: Division
        div = self._get_decision(product_name, self.hierarchy)
        if not div or div not in self.hierarchy: return None

        # Step 2: Group
        div_data = self.hierarchy[div]
        group = self._get_decision(product_name, div_data["groups"])
        if not group or group not in div_data["groups"]:
            return f"{div}.0.0.0", 0.6

        # Step 3: Class
        group_data = div_data["groups"][group]
        cls = self._get_decision(product_name, group_data["classes"])
        if not cls:
            return f"{group}.0.0", 0.7

        # Step 4: Sub-class (The 5th digit)
        # Some group_data might have a 'subclasses' map under each class
        if "classes" in group_data:
            class_data = group_data["classes"].get(cls)
            if isinstance(class_data, dict) and "subclasses" in class_data:
                subcls = self._get_decision(product_name, class_data["subclasses"])
                if subcls:
                    return subcls, 0.95

        return cls, 0.9

    def _verify_decision(self, product_name: str, code: str) -> bool:
        """Verifies a classification decision. Gemini 1.5 Flash acts as the Judge."""
        prompt = f"""You are a senior COICOP auditor.
Product: '{product_name}'
Assigned COICOP Code: {code}

Is this classification accurate according to COICOP 2018 standards?
Answer ONLY 'Yes' or 'No'. No explanation."""

        # Gemini acts as the Judge for quality assurance
        res = self._call_llm(prompt, model_type="gemini")
        return "yes" in res.lower()

    def classify_product(self, product_name: str, item_id: str = "NEW", store_slug: str = "") -> Dict[str, Any]:
        """Compatibility wrapper for creating new items without an existing ID."""
        res, _ = self.classify_debug(item_id, product_name, store_slug)
        return {
            "coicop_code": res['code'],
            "coicop_division": res['code'].split('.')[0].zfill(2) if '.' in res['code'] else res['code'],
            "coicop_method": res['method'],
            "confidence": res['confidence']
        }
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO silver.classification_cache (item_id, coicop_code, coicop_division, coicop_method, confidence)
                VALUES (%s, %s, split_part(%s, '.', 1), %s, %s)
                ON CONFLICT (item_id) DO UPDATE SET
                    coicop_code = EXCLUDED.coicop_code,
                    coicop_division = EXCLUDED.coicop_division,
                    coicop_method = EXCLUDED.coicop_method,
                    confidence = EXCLUDED.confidence,
                    classified_at = CURRENT_TIMESTAMP
            """, (item_id, code, code, method, confidence))
            conn.commit()
