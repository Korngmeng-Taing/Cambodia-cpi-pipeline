# Product Classification Methodology: The Hybrid Ladder

This document describes the robust, multi-stage classification pipeline used to assign high-accuracy 5-digit COICOP 2018 codes to scraped products.

## Overview
To minimize AI hallucinations and maximize throughput, the system employs a **"Hybrid Ladder"** approach. Instead of relying on a single AI prompt, the system attempts to classify a product using increasingly complex methods, starting with the fastest and most deterministic, and ending with the most "intelligent" but slowest.

---

## The Classification Pipeline (Silver Layer)

### 0. Canonicalization (Pre-processing)
Before entering the ladder, items are mapped to a **Canonical Name**. This ensures that slight variations in product naming (e.g., "Coke 330ml" vs "Coke 330ml Can") are treated as the same entity, reducing the number of expensive AI calls and ensuring consistency across the dataset.

### 1. The Cache Shortcut
**Method:** Direct Lookup  
**Logic:** The system checks the `silver.classification_cache` table for the `item_id`.  
**Outcome:** If a valid, non-unclassified classification already exists (excluding `UNCLASSIFIED`, `99`, or `REVIEW`), it is returned immediately. This is the fastest path and prevents redundant processing. If an unclassified or review flag exists in cache, the system automatically lets the product cascade down into the deterministic rule ladder.

### 2. Deterministic Rules
**Method:** Rule-based Matching  
**Logic:**
- **Store Purity:** If a product comes from a store known to sell exclusively one category of items (e.g., `realestate` / `khmer24` $\to$ `04`, `ppwsa` $\to$ `04`, `redbus` $\to$ `07`, `communitypharma` $\to$ `06`), the system assigns the verified division code for that store.
- **Critical Traps:** A library of keyword-based "traps" is checked using PostgreSQL regex with word boundaries (`\ypattern\y`). For example, "Panasonic Hair Dryer" is deterministically assigned to `12.1.1` (Personal Care) rather than generic appliances (`05`). Items matching traps are dynamically re-evaluated even during incremental runs.

### 3. Vector Fast-Lane (Semantic Search)
**Method:** Vector Embeddings (`pgvector` + `all-MiniLM-L6-v2`)  
**Logic:** The product name is converted into a high-dimensional vector. The system then performs a cosine similarity search against the **Gold Standard Table** (a library of human-verified product-to-code mappings).  
**Outcome:** If a semantic match is found with a high similarity score, the system adopts the verified code from the Gold Standard.

### 4. Hierarchical AI Drill-Down
**Method:** Multi-step LLM Reasoning (Llama 3.1 via Ollama)  
**Logic:** To avoid the "guessing" behavior of LLMs when asked for a 5-digit code, the system forces the AI to follow the COICOP 2018 structural hierarchy:
1. **Division (2 digits):** "Which broad category does this belong to?"
2. **Group (3 digits):** "Within that division, which group is most accurate?"
3. **Class (4 digits):** "Within that group, which class fits best?"
4. **Sub-class (5 digits):** "What is the final detailed code?"

This step-by-step approach drastically reduces hallucinations by providing the AI with a constrained list of valid options at each level.

### 5. The Gemini Judge (Final Audit)
**Method:** Adversarial Verification (Gemini 1.5 Flash)  
**Logic:** Once a 5-digit code is proposed by the Hierarchical AI, it is sent to a separate "Judge" model. The Judge is provided with the product name and the proposed code and asked a single question: *"Is this classification accurate according to COICOP 2018 standards? Answer ONLY 'Yes' or 'No'."*  
**Outcome:** 
- **Yes:** The classification is accepted.
- **No:** The system logs a "self-correction," rejects the code, and may attempt a fallback or mark the item for human review.

---

## Summary of the Data Flow

| Stage | Tool/Model | Type | Speed | Accuracy |
| :--- | :--- | :--- | :--- | :--- |
| **Cache** | PostgreSQL | Lookup | Instant | $\text{100\%}$ (Verified) |
| **Rules** | Regex/SQL | Deterministic | Instant | $\text{100\%}$ (Rule-based) |
| **Vector** | pgvector | Semantic | Fast | Very High |
| **AI Drill-Down** | Llama 3.1 | Generative | Slow | High |
| **Judge** | Gemini 1.5 | Audit | Medium | Highest |

## Final Output
The resulting classification (Code, Method, Confidence) is written to `silver.classification_cache`. This table then feeds into the `gold` layer, where it is used to aggregate daily prices and calculate the final CPI indices.
