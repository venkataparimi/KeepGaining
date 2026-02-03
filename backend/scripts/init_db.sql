-- KeepGaining Database Initialization Script
-- This script runs when the PostgreSQL container is first initialized

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- For text search
CREATE EXTENSION IF NOT EXISTS btree_gin; -- For GIN indexes on scalar types

-- Set timezone
SET timezone = 'Asia/Kolkata';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE keepgaining TO "user";

-- Create schemas
CREATE SCHEMA IF NOT EXISTS trading;
CREATE SCHEMA IF NOT EXISTS market_data;
CREATE SCHEMA IF NOT EXISTS audit;

-- Grant schema privileges
GRANT ALL PRIVILEGES ON SCHEMA trading TO "user";
GRANT ALL PRIVILEGES ON SCHEMA market_data TO "user";
GRANT ALL PRIVILEGES ON SCHEMA audit TO "user";

-- Note: Tables are created via Alembic migrations
-- This script only sets up the database infrastructure
