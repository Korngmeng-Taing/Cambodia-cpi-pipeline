-- pipeline/migrations/005_gold_geks.sql
-- DDL for Multilateral GEKS-Törnqvist index storage

CREATE TABLE IF NOT EXISTS gold.cpi_geks_multilateral (
    id SERIAL PRIMARY KEY,
    scrape_date DATE NOT NULL,
    base_period VARCHAR(16) NOT NULL DEFAULT '2026-08',
    window_size INT NOT NULL DEFAULT 13,
    formula VARCHAR(32) NOT NULL DEFAULT 'GEKS-Törnqvist',
    index_value NUMERIC(10, 4) NOT NULL,
    matched_items_count INT NOT NULL DEFAULT 0,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_geks_date_window UNIQUE (scrape_date, base_period, window_size)
);

CREATE INDEX IF NOT EXISTS idx_gold_geks_date ON gold.cpi_geks_multilateral (scrape_date);
