"""
pipeline/vector_item_matcher.py
───────────────────────────────
Semantic Product Matching using 768-dim Multilingual Vector Embeddings,
Deterministic Spec Guards, and Gemini Pro/Flash LLM Arbitration.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import numpy as np
from rapidfuzz import fuzz

from pipeline.key_pool import get_key_pool

try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:  # pragma: no cover
    genai = None
    HAS_GENAI = False

try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:  # pragma: no cover
    SentenceTransformer = None
    HAS_SENTENCE_TRANSFORMERS = False

log = logging.getLogger(__name__)

# Primary & Fallback Models
EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "models/text-embedding-004")
LLM_MODEL = os.getenv("GEMINI_PRO_MODEL", "gemini-2.5-flash")
LOCAL_FALLBACK_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# Known cross-lingual equivalences for Cambodian market
KHMER_ENGLISH_SYNONYMS = {
    "ស្រាបៀរអង្គរ": "angkor beer",
    "កូកាកូឡា": "coca cola",
    "ត្រីសាម៉ុង": "salmon",
    "សាំង": "gasoline",
    "សាច់គោ": "beef",
    "សាច់ជ្រូក": "pork",
    "សាច់មាន់": "chicken",
    "ទឹកដោះគោ": "milk",
}


def extract_specs(text: str) -> dict[str, Any]:
    """Extracts storage (GB/TB), volume (ml/L), mass (g/kg), and pack quantities to prevent false merges."""
    if not text:
        return {"storage": None, "pack_qty": 1, "size_val": None, "size_unit": None}

    t = text.lower()

    # 1. Electronics Storage (128GB, 256GB, 1TB)
    storage_match = re.search(r"\b(\d+)\s*(gb|tb)\b", t)
    storage = storage_match.group(0).replace(" ", "") if storage_match else None

    # 2. Pack size / Multiplier (x6, pack of 12, 6x330ml, x24 cans)
    pack_match = re.search(r"(?:pack of|pack|pk|x|\*)\s*(\d+)\b", t)
    pack_qty = int(pack_match.group(1)) if pack_match else 1

    # 3. Volume / Mass (330ml, 1.5L, 500g, 1kg)
    size_match = re.search(r"(\d+(?:\.\d+)?)\s*(kg|g|gm|l|ltr|ml)\b", t)
    size_val, size_unit = (float(size_match.group(1)), size_match.group(2)) if size_match else (None, None)
    if size_unit in ("gm", "g"):
        size_unit = "g"
    elif size_unit in ("ltr", "l"):
        size_unit = "l"

    return {
        "storage": storage,
        "pack_qty": pack_qty,
        "size_val": size_val,
        "size_unit": size_unit,
    }


def is_spec_compatible(cand_name: str, base_name: str) -> bool:
    """Deterministic guard: Rejects merges if physical specs or packaging quantities conflict."""
    cand_spec = extract_specs(cand_name)
    base_spec = extract_specs(base_name)

    # 1. Storage conflict (e.g. 128GB vs 256GB)
    if cand_spec["storage"] and base_spec["storage"] and cand_spec["storage"] != base_spec["storage"]:
        return False

    # 2. Pack quantity conflict (e.g. 1 can vs 6 pack)
    if cand_spec["pack_qty"] != base_spec["pack_qty"]:
        return False

    # 3. Size / Volume conflict (> 10% discrepancy within the same unit dimension)
    if cand_spec["size_val"] and base_spec["size_val"] and cand_spec["size_unit"] == base_spec["size_unit"]:
        ratio = abs(cand_spec["size_val"] - base_spec["size_val"]) / max(cand_spec["size_val"], base_spec["size_val"])
        if ratio > 0.10:
            return False

    # 4. Diet / Zero flavor vs Original flavor variant conflict
    cand_lower, base_lower = cand_name.lower(), base_name.lower()
    is_cand_diet = any(k in cand_lower for k in ("zero", "diet", "light", "no sugar"))
    is_base_diet = any(k in base_lower for k in ("zero", "diet", "light", "no sugar"))
    if is_cand_diet != is_base_diet:
        return False

    return True


def _build_semantic_item_vector(text: str) -> np.ndarray:
    """Deterministic, synonym-aware semantic token vector used in offline/test environments."""
    t_clean = text.lower()
    for kh, en in KHMER_ENGLISH_SYNONYMS.items():
        if kh in t_clean:
            t_clean += f" {en}"
    
    # Normalize common synonyms (e.g., Coke -> Coca-Cola)
    t_clean = re.sub(r"\bcoke\b", "coca cola", t_clean)

    tokens = set(re.findall(r"\b[a-zA-Z0-9]+\b", t_clean))
    vec = np.zeros(768, dtype=np.float32)

    for tok in tokens:
        h = abs(hash(tok)) % 768
        vec[h] += 1.0

    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


class VectorItemMatcher:
    """High-precision semantic item matcher powered by text-embedding-004 and Gemini Pro LLM."""

    def __init__(self) -> None:
        self.key_pool = get_key_pool()
        self._local_model = None

    def _get_local_model(self):
        if self._local_model is None and HAS_SENTENCE_TRANSFORMERS:
            try:
                self._local_model = SentenceTransformer(LOCAL_FALLBACK_MODEL)
            except Exception as e:
                log.warning("Could not load local sentence-transformers model: %s", e)
        return self._local_model

    def embed_text(self, text: str) -> np.ndarray:
        """Generates semantic dense embedding vector (768-dim via Gemini or 384-dim local)."""
        if not text or not text.strip():
            return np.zeros(768, dtype=np.float32)

        if HAS_GENAI and self.key_pool.get_key_count() > 0:
            def _call_gemini_embed(key: str) -> np.ndarray:
                genai.configure(api_key=key)
                res = genai.embed_content(model=EMBEDDING_MODEL, content=text.strip())
                return np.array(res["embedding"], dtype=np.float32)

            try:
                return self.key_pool.execute_with_retry(_call_gemini_embed)
            except Exception as exc:
                log.warning("Gemini embedding API failed; falling back to local model: %s", exc)

        local_model = self._get_local_model()
        if local_model is not None:
            vec = local_model.encode(text.strip())
            return np.array(vec, dtype=np.float32)

        return _build_semantic_item_vector(text)

    def match_candidate(
        self,
        candidate_name: str,
        catalog: list[dict[str, Any]],
        sim_auto_threshold: float = 0.80,
        sim_review_threshold: float = 0.65,
    ) -> dict[str, Any]:
        """Matches a scraped product name against candidate canonical items."""
        if not catalog:
            return {
                "decision": "SPLIT_NEW",
                "matched_item_id": None,
                "confidence": 1.0,
                "method": "new_item",
                "reason": "Catalog empty; created new canonical item.",
            }

        cand_vec = self.embed_text(candidate_name)
        cand_norm = np.linalg.norm(cand_vec)
        if cand_norm > 0:
            cand_unit = cand_vec / cand_norm
        else:
            cand_unit = cand_vec

        # Pre-ensure all catalog items have unit vectors
        vectors = []
        for item in catalog:
            ivec = item.get("vector")
            if ivec is None:
                ivec = self.embed_text(item.get("canonical_name", ""))
                inorm = np.linalg.norm(ivec)
                if inorm > 0:
                    ivec = ivec / inorm
                item["vector"] = ivec
            vectors.append(ivec)

        # Batch vector dot-product cosine similarity across all catalog items
        if vectors:
            mat = np.vstack(vectors)
            cos_sims = np.dot(mat, cand_unit)
        else:
            cos_sims = np.zeros(len(catalog), dtype=np.float32)

        best_item = None
        highest_sim = -1.0
        cand_lower = candidate_name.lower()

        # Fast filtering: evaluate spec compatibility and fuzzy booster
        for idx, item in enumerate(catalog):
            vec_sim = float(cos_sims[idx]) if idx < len(cos_sims) else 0.0
            
            # Fast prune if vector similarity is too low
            if vec_sim < 0.40 and highest_sim > 0.60:
                continue

            base_name = item.get("canonical_name", "")
            # Deterministic spec guard
            if not is_spec_compatible(candidate_name, base_name):
                continue

            # String token-sort fuzzy ratio fallback/booster
            fuzz_sim = fuzz.token_sort_ratio(cand_lower, base_name.lower()) / 100.0
            combined_sim = max(vec_sim, fuzz_sim)

            if combined_sim > highest_sim:
                highest_sim = combined_sim
                best_item = item

        # 1. High Confidence Vector/String Match (>= 0.80)
        if best_item and highest_sim >= sim_auto_threshold:
            return {
                "decision": "APPROVE_MATCH",
                "matched_item_id": str(best_item.get("item_id")),
                "confidence": round(highest_sim, 4),
                "method": "vector_embedding",
                "reason": f"High similarity ({highest_sim:.3f}) with {best_item.get('canonical_name')}",
                "coicop_code": best_item.get("coicop_code"),
                "coicop_division": best_item.get("coicop_division"),
            }

        # 2. Borderline Similarity (0.65 <= sim < 0.80) -> Arbitrate with Gemini LLM
        if best_item and highest_sim >= sim_review_threshold:
            return self.arbitrate_with_llm(candidate_name, best_item, highest_sim)

        # 3. Low Similarity (< 0.65) -> Brand new product
        return {
            "decision": "SPLIT_NEW",
            "matched_item_id": None,
            "confidence": 1.0,
            "method": "new_item",
            "reason": f"Top candidate similarity below threshold ({highest_sim:.3f} < {sim_review_threshold})",
        }

    def arbitrate_with_llm(
        self,
        candidate_name: str,
        best_item: dict[str, Any],
        sim_score: float,
    ) -> dict[str, Any]:
        """Sends ambiguous candidate pair to Gemini Pro/Flash for final arbitration."""
        canonical_name = best_item.get("canonical_name", "")
        item_id = str(best_item.get("item_id"))

        if not HAS_GENAI or self.key_pool.get_key_count() == 0:
            return {
                "decision": "APPROVE_MATCH" if sim_score >= 0.75 else "SPLIT_NEW",
                "matched_item_id": item_id if sim_score >= 0.75 else None,
                "confidence": round(sim_score, 4),
                "method": "vector_embedding_fallback",
                "reason": f"Vector fallback score {sim_score:.3f}",
            }

        prompt = f"""You are a master product entity matching expert for an official Consumer Price Index.
Compare these two product titles and decide if they represent the EXACT SAME physical product and packaging size sold across different retailers:

Candidate: "{candidate_name}"
Existing Canonical: "{canonical_name}"

Rules:
1. Return APPROVE_MATCH if they are identical products/sizes (including Khmer/English translations or brand synonyms).
2. Return SPLIT_NEW if they are different package sizes (e.g. 6-pack vs 1 can), different flavors, or different specs.

Return strict JSON only:
{{
  "decision": "APPROVE_MATCH" or "SPLIT_NEW",
  "confidence": float (0.0 to 1.0),
  "reason": "short explanation under 10 words"
}}"""

        def _call_llm(key: str) -> dict[str, Any]:
            genai.configure(api_key=key)
            model = genai.GenerativeModel(LLM_MODEL)
            resp = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"},
            )
            data = json.loads(resp.text)
            decision = data.get("decision", "SPLIT_NEW").strip().upper()
            return {
                "decision": "APPROVE_MATCH" if decision == "APPROVE_MATCH" else "SPLIT_NEW",
                "matched_item_id": item_id if decision == "APPROVE_MATCH" else None,
                "confidence": float(data.get("confidence", 0.90)),
                "method": "gemini_llm",
                "reason": str(data.get("reason", "LLM match review")),
                "coicop_code": best_item.get("coicop_code") if decision == "APPROVE_MATCH" else None,
                "coicop_division": best_item.get("coicop_division") if decision == "APPROVE_MATCH" else None,
            }

        try:
            return self.key_pool.execute_with_retry(_call_llm)
        except Exception as e:
            log.warning("LLM match review failed: %s. Falling back to SPLIT_NEW.", e)
            return {
                "decision": "SPLIT_NEW",
                "matched_item_id": None,
                "confidence": round(sim_score, 4),
                "method": "llm_error_fallback",
                "reason": f"LLM error fallback ({e})",
            }
