-- 013: Expression index for the Gemini AI cache name join.
-- int_coicop_classified joins dim_coicop_ai_cache on
--   lower(regexp_replace(trim(product_name), '\s+', ' ', 'g'))
-- Without this index every classified item re-normalizes the whole cache
-- (O(items x cache) regexp ops) — a full-history classification recompute
-- ran 20+ minutes before timing out; with the index it is an index lookup.
CREATE INDEX IF NOT EXISTS idx_ai_cache_norm_name
    ON silver.dim_coicop_ai_cache (lower(regexp_replace(trim(product_name), '\s+', ' ', 'g')));
