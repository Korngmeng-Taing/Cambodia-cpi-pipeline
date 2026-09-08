-- sql/migrations/0004_cold_storage_catalog.sql
-- ─────────────────────────────────────────────
-- Cold Storage Parquet Offloading Catalog for Cambodia CPI Pipeline.
--
-- Tracks immutable historical monthly partitions offloaded to compressed
-- Apache Parquet files, storing file paths, compression codec, row counts,
-- byte sizes, and cryptographic SHA-256 checksums for data integrity verification.

CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.cold_storage_catalog (
    id SERIAL PRIMARY KEY,
    schema_name VARCHAR(64) NOT NULL,
    parent_table VARCHAR(64) NOT NULL,
    partition_name VARCHAR(128) NOT NULL,
    year INT NOT NULL,
    month INT NOT NULL,
    parquet_path TEXT NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    row_count BIGINT NOT NULL,
    sha256_checksum VARCHAR(64) NOT NULL,
    compression VARCHAR(32) NOT NULL DEFAULT 'zstd',
    min_timestamp TIMESTAMPTZ,
    max_timestamp TIMESTAMPTZ,
    exported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status VARCHAR(32) NOT NULL DEFAULT 'verified',
    CONSTRAINT uq_cold_storage_partition UNIQUE (schema_name, partition_name)
);

CREATE INDEX IF NOT EXISTS idx_cold_storage_table_period 
    ON ops.cold_storage_catalog (schema_name, parent_table, year, month);

CREATE INDEX IF NOT EXISTS idx_cold_storage_status 
    ON ops.cold_storage_catalog (status);

COMMENT ON TABLE ops.cold_storage_catalog IS
    'Catalog of historical partition microdata offloaded from PostgreSQL to compressed Apache Parquet cold storage.';
