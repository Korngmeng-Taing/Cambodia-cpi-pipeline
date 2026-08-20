-- =============================================================================
-- CAMBODIA CPI PIPELINE — POSTGRESQL INITIALIZATION
-- Sets up databases for Airflow, Metabase, and CPI Application
-- =============================================================================

-- 1. Airflow Metadata Database
CREATE USER airflow WITH PASSWORD 'airflow';
CREATE DATABASE airflow OWNER airflow;
GRANT ALL PRIVILEGES ON DATABASE airflow TO airflow;

-- 2. CPI Pipeline Application Database
CREATE USER cpi_user WITH PASSWORD 'cpi_pass';
CREATE DATABASE cpi_db OWNER cpi_user;
GRANT ALL PRIVILEGES ON DATABASE cpi_db TO cpi_user;

-- 3. Metabase Application Database
CREATE USER metabase WITH PASSWORD 'metabase';
CREATE DATABASE metabase OWNER metabase;
GRANT ALL PRIVILEGES ON DATABASE metabase TO metabase;

-- Connect to cpi_db to initialize CPI schemas, procedures, and views
\connect cpi_db

-- Grant schema creation rights and permissions
GRANT ALL ON SCHEMA public TO cpi_user;

-- Execute DDL definitions
\i /sql/schema.sql
\i /sql/views.sql
\i /sql/gold_procedures.sql

-- Transfer ownership of all pipeline objects to cpi_user so DDL run by the
-- application user (e.g. DROP VIEW / ALTER COLUMN TYPE) is permitted.
-- Sequences linked to tables follow their table's owner automatically.
DO $$
DECLARE
    obj RECORD;
    typ text;
BEGIN
    FOR obj IN
        SELECT n.nspname AS schema_name, c.relname AS obj_name, c.relkind
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname IN ('staging','silver','gold')
          AND c.relkind IN ('r','p','v','m')
          AND pg_get_userbyid(c.relowner) <> 'cpi_user'
    LOOP
        typ := CASE obj.relkind
                 WHEN 'r' THEN 'TABLE'
                 WHEN 'p' THEN 'TABLE'
                 WHEN 'v' THEN 'VIEW'
                 WHEN 'm' THEN 'MATERIALIZED VIEW'
               END;
        EXECUTE format('ALTER %s %I.%I OWNER TO cpi_user', typ, obj.schema_name, obj.obj_name);
    END LOOP;
END $$;

-- Transfer ownership of functions/procedures in pipeline schemas to cpi_user.
DO $$
DECLARE
    fn RECORD;
    obj_kind text;
BEGIN
    FOR fn IN
        SELECT p.oid::regprocedure::text AS sig, p.prokind
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname IN ('staging','silver','gold')
          AND pg_get_userbyid(p.proowner) <> 'cpi_user'
    LOOP
        obj_kind := CASE WHEN fn.prokind = 'p' THEN 'PROCEDURE' ELSE 'FUNCTION' END;
        EXECUTE format('ALTER %s %s OWNER TO cpi_user', obj_kind, fn.sig);
    END LOOP;
END $$;

-- Grant all permissions on created schemas, tables, sequences, functions, procedures to cpi_user
GRANT ALL ON SCHEMA staging TO cpi_user;
GRANT ALL ON SCHEMA silver TO cpi_user;
GRANT ALL ON SCHEMA gold TO cpi_user;

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA staging TO cpi_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA silver TO cpi_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA gold TO cpi_user;

GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA staging TO cpi_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA silver TO cpi_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA gold TO cpi_user;

GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA staging TO cpi_user;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA silver TO cpi_user;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA gold TO cpi_user;

GRANT ALL PRIVILEGES ON ALL PROCEDURES IN SCHEMA gold TO cpi_user;

ALTER DEFAULT PRIVILEGES IN SCHEMA staging GRANT ALL ON TABLES TO cpi_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA silver GRANT ALL ON TABLES TO cpi_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA gold GRANT ALL ON TABLES TO cpi_user;

ALTER DEFAULT PRIVILEGES IN SCHEMA staging GRANT ALL ON SEQUENCES TO cpi_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA silver GRANT ALL ON SEQUENCES TO cpi_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA gold GRANT ALL ON SEQUENCES TO cpi_user;

ALTER DEFAULT PRIVILEGES IN SCHEMA staging GRANT ALL ON FUNCTIONS TO cpi_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA silver GRANT ALL ON FUNCTIONS TO cpi_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA gold GRANT ALL ON FUNCTIONS TO cpi_user;
