-- test_no_aeon_in_coicop_06
-- Sanity guard for AEON 1 / AEON 3 (supermarket).
--
-- HISTORY: this used to ban division 06 (Health / Pharmaceuticals) at AEON
-- outright. That was wrong: AEON genuinely stocks OTC medicine (throat
-- lozenges, cough drops, vitamins...), and live data proved it — Gemini
-- correctly classified 'GOLDEN THROAT LOZENGE PACK/BOX' and 'MANUKA HONEY
-- COUGH DROPS' as 06.1.2.
--
-- NEW CONTRACT: high-signal classification methods are TRUSTED at AEON:
--   * override        — human authority
--   * gemini_ai       — AI cache, already gated to confidence >= 0.50 by the
--                       ladder (low-confidence rows land in REVIEW, not 06)
--   * exception       — deterministic trap regexes (clinic/hospital services…)
-- Weak heuristic guesses (keyword_ladder / category_map) putting random
-- supermarket goods into Health remain a failure.
select
    item_id,
    store_slug,
    canonical_name,
    coicop_division,
    coicop_method,
    coicop_confidence
from {{ ref('int_coicop_classified') }}
where store_slug in ('aeon', 'aeon3')
  and coicop_division = '06'
  and coicop_method not in ('override', 'gemini_ai', 'exception', 'category_map')
