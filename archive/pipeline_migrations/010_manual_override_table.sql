-- =============================================================================
-- 010_manual_override_table.sql
-- Separate table for labeling-app overrides.
--
-- Why: silver.coicop_override is owned by the dbt seed
-- dbt/seeds/coicop_override.csv and is fully recreated on every
-- `dbt seed`, which silently wiped rows written by apps/labeling_app.py.
-- Manual triage decisions now go to silver.coicop_override_manual;
-- int_coicop_classified UNIONs both tables at query time.
-- =============================================================================

CREATE TABLE IF NOT EXISTS silver.coicop_override_manual (
    id SERIAL PRIMARY KEY,
    match_type VARCHAR(32) NOT NULL, -- 'product_key', 'barcode', 'name'
    match_value TEXT NOT NULL,
    store_slug VARCHAR(64), -- NULL applies to all stores
    coicop_division VARCHAR(16) NOT NULL,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_override_manual_match ON silver.coicop_override_manual(match_type, match_value);

-- Migrate any manual rows that were previously written into the seed-owned
-- table but are absent from the seed CSV (best effort; ignore conflicts).
-- Note: the seed table has no created_at column (it mirrors the CSV),
-- so stamp migrated rows with NOW().
INSERT INTO silver.coicop_override_manual (match_type, match_value, store_slug, coicop_division, reason, created_at)
SELECT o.match_type, o.match_value, o.store_slug, o.coicop_division, o.reason, NOW()
FROM silver.coicop_override o
WHERE NOT EXISTS (
    SELECT 1
    FROM silver.coicop_override_manual m
    WHERE m.match_type = o.match_type
      AND trim(m.match_value) = trim(o.match_value)
      AND COALESCE(m.store_slug, '') = COALESCE(o.store_slug, '')
      AND m.coicop_division = o.coicop_division
);
