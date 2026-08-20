-- =============================================================================
-- 006_coicop_classification.sql
-- Foundation + lookup tables for rule-based and ML COICOP classification.
--
-- - Ensures silver.dim_canonical_products exists (matches sql/schema.sql; the
--   running database predates the canonicalizer tables) and adds the ML output
--   columns used by pipeline/ml_coicop_classifier.py.
-- - Creates the rule-based lookup tables:
--     silver.dim_coicop_keywords   (keywords array, used by stg_coicop_mapping)
--     silver.dim_coicop_rules      (keyword/regex rules, used by stg_rule_based_classification)
--     silver.dim_coicop_hierarchy  (official code reference, used by the dbt
--                                   coverage test test_coicop_coverage.sql)
-- - Seeds a few demo canonical products so the classification pipeline can be
--   exercised end-to-end.
--
-- Idempotent: safe to re-run. Applied to the running DB with:
--   psql -U cpi_user -d cpi_db -f pipeline/migrations/006_coicop_classification.sql
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS silver;

-- -----------------------------------------------------------------------------
-- 1. dim_canonical_products foundation + ML output columns
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.dim_canonical_products (
    canonical_item_id UUID PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    coicop_code VARCHAR(16),
    source_name VARCHAR(64),
    raw_item_id VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_dim_canonical_raw_item
    ON silver.dim_canonical_products(source_name, raw_item_id);

ALTER TABLE silver.dim_canonical_products
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS ml_confidence NUMERIC(5, 4),
    ADD COLUMN IF NOT EXISTS classification_method VARCHAR(32),
    ADD COLUMN IF NOT EXISTS needs_review BOOLEAN NOT NULL DEFAULT FALSE;

-- -----------------------------------------------------------------------------
-- 2. Rule-based keyword lookup (Prompt 1)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.dim_coicop_keywords (
    coicop_code VARCHAR(16) NOT NULL,
    category_name TEXT NOT NULL,
    keywords TEXT[] NOT NULL,
    PRIMARY KEY (coicop_code)
);

INSERT INTO silver.dim_coicop_keywords (coicop_code, category_name, keywords) VALUES
    ('01.1.1', 'Bread and cereals',            ARRAY['bread', 'rice', 'noodle', 'pasta', 'flour', 'cereal', 'oatmeal']),
    ('01.1.4', 'Milk, cheese and eggs',        ARRAY['milk', 'cheese', 'yogurt', 'yoghurt', 'butter', 'egg', 'cream']),
    ('01.1.8', 'Oils and fats',                ARRAY['oil', 'margarine', 'cooking oil', 'olive oil', 'lard']),
    ('04.1.1', 'Actual rentals for housing',   ARRAY['rent', 'apartment', 'condo rent']),
    ('04.5.1', 'Electricity',                  ARRAY['electricity', 'power bill', 'kwh']),
    ('05.3.1', 'Major household appliances',   ARRAY['refrigerator', 'washing machine', 'rice cooker', 'air conditioner']),
    ('05.6.1', 'Non-durable household goods',  ARRAY['detergent', 'soap', 'cleaning', 'dish soap', 'laundry']),
    ('07.2.2', 'Fuels and lubricants',         ARRAY['gasoline', 'diesel', 'petrol', 'fuel', 'engine oil']),
    ('08.2.0', 'Telephone and telefax equipment', ARRAY['smartphone', 'mobile', 'iphone', 'handset']),
    ('09.3.1', 'Games, toys and hobbies',      ARRAY['toy', 'doll', 'puzzle', 'chess', 'board game'])
ON CONFLICT (coicop_code) DO NOTHING;

-- -----------------------------------------------------------------------------
-- 3. Rule-based keyword/regex rules (Prompt 4) with 10 realistic examples
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.dim_coicop_rules (
    rule_id SERIAL PRIMARY KEY,
    coicop_code VARCHAR(16) NOT NULL,
    category_name TEXT NOT NULL,
    match_type VARCHAR(16) NOT NULL CHECK (match_type IN ('keyword', 'regex')),
    pattern TEXT NOT NULL,
    CONSTRAINT uq_coicop_rule UNIQUE (coicop_code, match_type, pattern)
);

INSERT INTO silver.dim_coicop_rules (coicop_code, category_name, match_type, pattern) VALUES
    ('01.1.1', 'Bread and cereals',           'keyword', 'bread'),
    ('01.1.1', 'Bread and cereals',           'keyword', 'rice'),
    ('01.1.4', 'Milk, cheese and eggs',       'keyword', 'milk'),
    ('01.1.4', 'Milk, cheese and eggs',       'regex',   'cheese|yog(h)?urt|butter|\\bcream\\b'),
    ('01.1.8', 'Oils and fats',               'regex',   '(olive|sunflower|cooking)?\\s*oil\\b|margarine'),
    ('04.5.1', 'Electricity',                 'regex',   'electricity|\\bkwh\\b|power\\s+(bill|tariff)'),
    ('05.6.1', 'Non-durable household goods', 'keyword', 'detergent'),
    ('07.2.2', 'Fuels and lubricants',        'regex',   'gasoline|diesel|petrol|\\bfuel\\b'),
    ('08.2.0', 'Telephone and telefax equipment', 'regex', 'smartphone|iphone|mobile\\s*phone|\\bhandset\\b'),
    ('09.3.1', 'Games, toys and hobbies',     'keyword', 'toy')
ON CONFLICT (coicop_code, match_type, pattern) DO NOTHING;

-- -----------------------------------------------------------------------------
-- 4. Official COICOP hierarchy reference (used by test_coicop_coverage.sql)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.dim_coicop_hierarchy (
    coicop_code VARCHAR(16) PRIMARY KEY,
    category_name TEXT NOT NULL,
    parent_code VARCHAR(16),
    level SMALLINT NOT NULL
);

INSERT INTO silver.dim_coicop_hierarchy (coicop_code, category_name, parent_code, level) VALUES
    ('01',       'Food and non-alcoholic beverages',   NULL, 1),
    ('01.1',     'Food',                                '01', 2),
    ('01.1.1',   'Bread and cereals',                   '01.1', 3),
    ('01.1.4',   'Milk, cheese and eggs',               '01.1', 3),
    ('01.1.8',   'Oils and fats',                       '01.1', 3),
    ('02',       'Alcoholic beverages and tobacco',     NULL, 1),
    ('02.1.1',   'Spirits',                             '02.1', 3),
    ('02.2.0',   'Tobacco',                             '02.2', 3),
    ('04',       'Housing, water, electricity, gas and other fuels', NULL, 1),
    ('04.1.1',   'Actual rentals for housing',          '04.1', 3),
    ('04.5.1',   'Electricity',                         '04.5', 3),
    ('05',       'Furnishings, household equipment and routine maintenance', NULL, 1),
    ('05.3.1',   'Major household appliances',          '05.3', 3),
    ('05.6.1',   'Non-durable household goods',         '05.6', 3),
    ('07',       'Transport',                           NULL, 1),
    ('07.2.2',   'Fuels and lubricants for personal transport equipment', '07.2', 3),
    ('08',       'Communication',                       NULL, 1),
    ('08.2.0',   'Telephone and telefax equipment',     '08.2', 3),
    ('09',       'Recreation and culture',              NULL, 1),
    ('09.3.1',   'Games, toys and hobbies',             '09.3', 3),
    ('12',       'Miscellaneous goods and services',    NULL, 1),
    ('12.1.3',   'Articles and products for personal care', '12.1', 3),
    ('99.9.9',   'Unclassified',                        NULL, 3)
ON CONFLICT (coicop_code) DO NOTHING;

-- -----------------------------------------------------------------------------
-- 5. Demo canonical products (placeholder 99.9.9 so the ML classifier and dbt
--    coverage test can be exercised).
-- -----------------------------------------------------------------------------
INSERT INTO silver.dim_canonical_products
    (canonical_item_id, canonical_name, coicop_code, source_name, raw_item_id)
VALUES
    (gen_random_uuid(), 'Fresh Whole Milk 1L',    '99.9.9', 'supermarket_a', 'SEED-MILK-01'),
    (gen_random_uuid(), 'Smartphone Galaxy 8GB/256GB', '99.9.9', 'electronics_store', 'SEED-PHONE-01'),
    (gen_random_uuid(), 'Diesel Fuel',            '99.9.9', 'tela', 'SEED-DIESEL-01'),
    (gen_random_uuid(), 'Washing Detergent 2kg',  '99.9.9', 'grocery_chain', 'SEED-DETERGENT-01'),
    (gen_random_uuid(), 'Organic Bananas',        '99.9.9', 'supermarket_a', 'SEED-BANANA-01')
ON CONFLICT (source_name, raw_item_id) DO NOTHING;