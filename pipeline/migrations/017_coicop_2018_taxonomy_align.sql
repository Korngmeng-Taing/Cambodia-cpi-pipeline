-- migrations/017_coicop_2018_taxonomy_align.sql
-- =============================================================================
-- UN COICOP 2018 TAXONOMY MIGRATION
-- =============================================================================
-- Updates legacy 1999 COICOP class codes in silver tables to the official
-- UN COICOP 2018 standard (e.g. 05.2.0 -> 05.2.1, 05.4.0 -> 05.5.1).

DO $$
BEGIN
    -- 1. Migrate AI Cache table if it exists
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'silver' AND table_name = 'dim_coicop_ai_cache'
    ) THEN
        UPDATE silver.dim_coicop_ai_cache
        SET coicop_code = '05.2.1'
        WHERE coicop_code = '05.2.0';

        UPDATE silver.dim_coicop_ai_cache
        SET coicop_code = '05.5.1'
        WHERE coicop_code = '05.4.0';

        RAISE NOTICE 'Updated legacy COICOP codes in silver.dim_coicop_ai_cache';
    END IF;

    -- 2. Migrate Canonical Items table if it exists
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'silver' AND table_name = 'canonical_items'
    ) THEN
        UPDATE silver.canonical_items
        SET coicop_code = '05.2.1'
        WHERE coicop_code = '05.2.0';

        UPDATE silver.canonical_items
        SET coicop_code = '05.5.1'
        WHERE coicop_code = '05.4.0';

        RAISE NOTICE 'Updated legacy COICOP codes in silver.canonical_items';
    END IF;

    -- 3. Migrate Clean Store Prices table if it exists
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'silver' AND table_name = 'clean_store_prices'
    ) THEN
        UPDATE silver.clean_store_prices
        SET coicop_code = '05.2.1'
        WHERE coicop_code = '05.2.0';

        UPDATE silver.clean_store_prices
        SET coicop_code = '05.5.1'
        WHERE coicop_code = '05.4.0';

        RAISE NOTICE 'Updated legacy COICOP codes in silver.clean_store_prices';
    END IF;

    -- 4. Migrate Elementary Indices table if it exists
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'gold' AND table_name = 'fct_elementary_indices'
    ) THEN
        UPDATE gold.fct_elementary_indices
        SET coicop_code = '05.2.1'
        WHERE coicop_code = '05.2.0';

        UPDATE gold.fct_elementary_indices
        SET coicop_code = '05.5.1'
        WHERE coicop_code = '05.4.0';

        RAISE NOTICE 'Updated legacy COICOP codes in gold.fct_elementary_indices';
    END IF;
END $$;
