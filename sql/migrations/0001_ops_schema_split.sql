-- P3 #123 — Idempotent migration to create ops schema and alias views.
-- Safe to re-run: creates schema, then CREATE OR REPLACE VIEW for each table.
-- No data movement; silver.* tables remain the canonical storage.

CREATE SCHEMA IF NOT EXISTS ops;

COMMENT ON SCHEMA ops IS
    'P3 #123 — Operational & control-flow tables (overrides, review queues, AI cache) live here. '
    'silver.* views on the same names are kept as legacy pass-through for existing writers.';

-- Each view is a pass-through to the silver.* table so writers continue
-- to INSERT/UPDATE silver.* (unchanged) and readers can use ops.*.
CREATE OR REPLACE VIEW ops.coicop_override          AS SELECT * FROM silver.coicop_override;
CREATE OR REPLACE VIEW ops.coicop_override_manual   AS SELECT * FROM silver.coicop_override_manual;
CREATE OR REPLACE VIEW ops.coicop_category_map      AS SELECT * FROM silver.coicop_category_map;
CREATE OR REPLACE VIEW ops.classification_queue      AS SELECT * FROM silver.classification_queue;
CREATE OR REPLACE VIEW ops.dim_coicop_ai_cache       AS SELECT * FROM silver.dim_coicop_ai_cache;

-- Backwards-compat: grant same privileges as silver (if custom perms exist)
-- GRANT SELECT ON ALL TABLES IN SCHEMA ops TO cpi_readonly;