"""
pipeline/vector_item_matcher.py
───────────────────────────────
Semantic Product Matching using 768-dim Multilingual Vector Embeddings,
Deterministic Spec Guards, and Gemini Pro/Flash AI Arbitration.
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
from pipeline.text_clean import is_size_compatible

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
EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-2")
LLM_MODEL = os.getenv("GEMINI_PRO_MODEL", "gemini-3.5-flash")
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

    # 2. Pack size / Multiplier (e.g. 24x330ml, 6 x 500ml, pack of 12, case of 24, 24 cans, 6 bottles, 6pk)
    pack_match = re.search(
        r"(?:(\d+)\s*(?:x|\*)\s*\d+(?:\.\d+)?\s*(?:ml|l|g|kg|gm|ltr)\b)"
        r"|(?:(?:pack of|case of|pack|pk|box of)\s*(\d+)\b)"
        r"|(?:\b(\d+)\s*(?:cans?|bottles?|packs?|pcs?|pieces?|pk)\b)"
        r"|(?:(?:x|\*)\s*(\d+)\b)",
        t,
    )
    if pack_match:
        matched_groups = [g for g in pack_match.groups() if g is not None]
        pack_qty = int(matched_groups[0]) if matched_groups else 1
    else:
        pack_qty = 1

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
    # H2 FIX: Use shared is_size_compatible which cross-normalizes g↔kg and ml↔L
    cand_size = f"{cand_spec['size_val']}{cand_spec['size_unit']}" if cand_spec["size_val"] and cand_spec["size_unit"] else None
    base_size = f"{base_spec['size_val']}{base_spec['size_unit']}" if base_spec["size_val"] and base_spec["size_unit"] else None
    if not is_size_compatible(cand_size, base_size, tolerance=0.10):
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
    """High-precision semantic item matcher powered by Gemini Embedding 2 and Gemini Flash LLM."""

    def __init__(self) -> None:
        self.key_pool = get_key_pool()
        self._local_model = None
        self._embed_cache: dict[str, np.ndarray] = {}

    def _get_local_model(self):
        if self._local_model is None and HAS_SENTENCE_TRANSFORMERS:
            try:
                self._local_model = SentenceTransformer(LOCAL_FALLBACK_MODEL)
            except Exception as e:
                log.warning("Could not load local sentence-transformers model: %s", e)
        return self._local_model

    def embed_text(self, text: str) -> np.ndarray:
        """Generates semantic dense embedding vector (768-dim via local fallback or Gemini)."""
        if not text or not text.strip():
            return np.zeros(768, dtype=np.float32)

        cleaned_text = text.strip()
        if cleaned_text in self._embed_cache:
            return self._embed_cache[cleaned_text]

        # Fast local embedding mode enabled by default to prevent API quota 429 delays
        use_local_first = os.getenv("USE_LOCAL_FALLBACK_FIRST", "true").lower() in ("true", "1", "yes")
        if not use_local_first and HAS_GENAI and self.key_pool.get_key_count() > 0:
            def _call_gemini_embed(key: str) -> np.ndarray:
                genai.configure(api_key=key)
                res = genai.embed_content(model=EMBEDDING_MODEL, content=cleaned_text)
                return np.array(res["embedding"], dtype=np.float32)

            try:
                vec = self.key_pool.execute_with_retry(_call_gemini_embed)
                self._embed_cache[cleaned_text] = vec
                return vec
            except Exception as exc:
                log.warning("Gemini embedding API failed; falling back to local model: %s", exc)

        local_model = self._get_local_model()
        if local_model is not None:
            vec = local_model.encode(cleaned_text)
            local_vec = np.array(vec, dtype=np.float32)
            # Ensure consistent 768-dim: local model may return 384-dim, pad or project to 768
            if local_vec.shape[0] < 768:
                padded = np.zeros(768, dtype=np.float32)
                padded[: local_vec.shape[0]] = local_vec
                self._embed_cache[cleaned_text] = padded
                return padded
            result_vec = local_vec[:768]
            self._embed_cache[cleaned_text] = result_vec
            return result_vec

        res_vec = _build_semantic_item_vector(cleaned_text)
        self._embed_cache[cleaned_text] = res_vec
        return res_vec

    def embed_texts(self, texts: list[str], batch_size: int = 256) -> np.ndarray:
        """Generates semantic dense embedding vectors in batched tensor passes for speed."""
        if not texts:
            return np.zeros((0, 768), dtype=np.float32)

        result = np.zeros((len(texts), 768), dtype=np.float32)
        to_encode_indices: list[int] = []
        to_encode_texts: list[str] = []

        for i, t in enumerate(texts):
            cleaned = t.strip() if t else ""
            if not cleaned:
                continue
            if cleaned in self._embed_cache:
                result[i] = self._embed_cache[cleaned]
            else:
                to_encode_indices.append(i)
                to_encode_texts.append(cleaned)

        if not to_encode_texts:
            return result

        local_model = self._get_local_model()
        if local_model is not None:
            try:
                batch_vecs = local_model.encode(
                    to_encode_texts, batch_size=batch_size, show_progress_bar=False
                )
                batch_np = np.array(batch_vecs, dtype=np.float32)
                if batch_np.shape[1] < 768:
                    padded = np.zeros((batch_np.shape[0], 768), dtype=np.float32)
                    padded[:, : batch_np.shape[1]] = batch_np
                    batch_np = padded
                else:
                    batch_np = batch_np[:, :768]

                for idx, orig_idx in enumerate(to_encode_indices):
                    vec = batch_np[idx]
                    cleaned = to_encode_texts[idx]
                    self._embed_cache[cleaned] = vec
                    result[orig_idx] = vec
                return result
            except Exception as e:
                log.warning("Batch encoding with local model failed: %s", e)

        for idx, orig_idx in enumerate(to_encode_indices):
            cleaned = to_encode_texts[idx]
            vec = self.embed_text(cleaned)
            result[orig_idx] = vec
        return result

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

        # Pre-ensure all catalog items have unit vectors and cache the matrix
        if hasattr(catalog, "_cached_matrix") and getattr(catalog, "_cached_matrix_len", 0) == len(catalog):
            mat = catalog._cached_matrix
        else:
            missing_items = [item for item in catalog if item.get("vector") is None]
            if missing_items:
                missing_names = [item.get("canonical_name", "") for item in missing_items]
                missing_vecs = self.embed_texts(missing_names, batch_size=256)
                for i, item in enumerate(missing_items):
                    ivec = missing_vecs[i]
                    inorm = np.linalg.norm(ivec)
                    if inorm > 0:
                        ivec = ivec / inorm
                    item["vector"] = ivec

            vectors = [item["vector"] for item in catalog if item.get("vector") is not None]
            if vectors:
                mat = np.vstack(vectors)
            else:
                mat = np.zeros((0, 768), dtype=np.float32)
            try:
                catalog._cached_matrix = mat
                catalog._cached_matrix_len = len(catalog)
            except (AttributeError, TypeError):
                pass

        if mat.shape[0] > 0:
            cos_sims = np.dot(mat, cand_unit)
        else:
            cos_sims = np.zeros(len(catalog), dtype=np.float32)

        best_item = None
        highest_sim = -1.0
        cand_lower = candidate_name.lower()

        # Fast filtering: evaluate only top-K vector candidate neighbors instead of full O(M) loop
        n_items = len(catalog)
        if n_items > 30:
            top_indices = np.argpartition(cos_sims, -30)[-30:]
            # Sort top 30 descending by cosine similarity
            top_indices = top_indices[np.argsort(cos_sims[top_indices])[::-1]]
        else:
            top_indices = range(n_items)

        for idx in top_indices:
            item = catalog[idx]
            vec_sim = float(cos_sims[idx]) if idx < len(cos_sims) else 0.0

            # Early exit if vector similarity is too low and we already have a strong match
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

        # 2. Borderline Similarity (0.65 <= sim < 0.80) -> Arbitrate with Gemini AI
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
        """Sends ambiguous candidate pair to Gemini Pro/Flash or uses local thresholding in local-first mode."""
        canonical_name = best_item.get("canonical_name", "")
        item_id = str(best_item.get("item_id"))

        use_local_first = os.getenv("USE_LOCAL_FALLBACK_FIRST", "true").lower() in ("true", "1", "yes")
        if use_local_first or not HAS_GENAI or self.key_pool.get_key_count() == 0:
            is_match = sim_score >= 0.75
            return {
                "decision": "APPROVE_MATCH" if is_match else "SPLIT_NEW",
                "matched_item_id": item_id if is_match else None,
                "confidence": round(sim_score, 4),
                "method": "vector_embedding_local",
                "reason": f"Local vector score {sim_score:.3f}",
                "coicop_code": best_item.get("coicop_code") if is_match else None,
                "coicop_division": best_item.get("coicop_division") if is_match else None,
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
