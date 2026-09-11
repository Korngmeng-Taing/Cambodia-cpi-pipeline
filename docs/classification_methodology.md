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

### 3. AI-First Direct Classification (Gemini Flash)
**Method:** One-shot Structured Reasoning with Domain Guardrails (Gemini Flash via `GeminiKeyPool`)  
**Logic:** Rather than relying on slow multi-step local LLM chains, the production pipeline utilizes Google Gemini Flash equipped with complete UN COICOP 2018 hierarchical classification taxonomy and domain guardrails (e.g., pet foods, personal care, supermarket meals, alcohol, and medicines).
- **Direct 5-Digit Resolution:** Concurrently predicts 2-digit division, 4-digit class, and 5-digit sub-class code along with official name and rationale in structured JSON format.
- **Bilingual Comprehension:** Natively handles mixed and pure Khmer retail titles and descriptions without separate translation layers.
- **Batch Processing:** Processes 40 products per API payload with automatic multi-key rotation and 429 failover.

---

## Summary of the Data Flow

| Stage | Tool/Model | Type | Speed | Accuracy |
| :--- | :--- | :--- | :--- | :--- |
| **Cache** | PostgreSQL | Lookup | Instant | $\text{100\%}$ (Verified) |
| **Rules** | Regex/SQL | Deterministic | Instant | $\text{100\%}$ (Rule-based) |
| **AI Engine** | Gemini Flash | Generative / Structured | High-speed batch | Highest |

## Final Output
The resulting classification (Code, Method, Confidence) is written to `silver.classification_cache`. This table then feeds into the `gold` layer, where it is used to aggregate daily prices and calculate the final CPI indices.
