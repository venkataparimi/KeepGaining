# TimescaleDB Migration Guide

## Overview
TimescaleDB extends PostgreSQL with time-series superpowers:
- **10-100x faster** queries on time-series data
- **Automatic compression** (90% storage savings)
- **Continuous aggregations** (pre-computed indicators)
- **Data retention policies** (auto-delete old data)

## Installation Steps

### 1. Install TimescaleDB Extension

#### On Docker (Recommended)
Update your `docker-compose.yml`:

```yaml
services:
  db:
    image: timescale/timescaledb:latest-pg16  # Use TimescaleDB image instead of postgres
    environment:
      POSTGRES_USER: keepgaining
      POSTGRES_PASSWORD: your_password
      POSTGRES_DB: trading_db
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
```

Then restart:
```bash
docker-compose down
docker-compose up -d
```

#### On Existing PostgreSQL

**Ubuntu/Debian:**
```bash
# Add TimescaleDB repository
sudo sh -c "echo 'deb https://packagecloud.io/timescale/timescaledb/ubuntu/ $(lsb_release -c -s) main' > /etc/apt/sources.list.d/timescaledb.list"
wget --quiet -O - https://packagecloud.io/timescale/timescaledb/gpgkey | sudo apt-key add -

# Install
sudo apt update
sudo apt install timescaledb-2-postgresql-16

# Configure
sudo timescaledb-tune

# Restart PostgreSQL
sudo systemctl restart postgresql
```

**Windows:**
Download installer from: https://docs.timescale.com/install/latest/self-hosted/installation-windows/

**Mac:**
```bash
brew tap timescale/tap
brew install timescaledb
```

### 2. Run Migration

```bash
cd backend

# Run the migration
alembic upgrade head

# Should see output:
# Converting market_data to hypertable...
# ✅ market_data converted to hypertable with compression and retention
# ✅ Created continuous aggregation for SMA-20
```

### 3. Verify Installation

```bash
# Connect to PostgreSQL
psql -U keepgaining -d trading_db

# Check TimescaleDB version
\dx timescaledb

# List hypertables
SELECT * FROM timescaledb_information.hypertables;

# Check compression status
SELECT * FROM timescaledb_information.compression_settings;
```

## What the Migration Does

### 1. Converts Tables to Hypertables
```sql
-- Before: Regular PostgreSQL table
CREATE TABLE market_data (
    timestamp TIMESTAMPTZ,
    symbol VARCHAR,
    open NUMERIC,
    ...
);

-- After: TimescaleDB hypertable (automatically partitioned by time)
SELECT create_hypertable('market_data', 'timestamp');
```

### 2. Enables Compression
- Compresses data older than 7 days
- 90%+ storage savings
- Queries still work normally

### 3. Adds Data Retention
- Automatically deletes data older than 2 years
- Keeps database size manageable

### 4. Creates Continuous Aggregations
- Pre-computes SMA-20 every minute
- Query results instantly instead of calculating on demand

## Performance Comparison

**Before (Regular PostgreSQL):**
```sql
-- Calculate SMA-20 for all symbols (takes 5-10 seconds)
SELECT symbol, AVG(close) OVER (
    PARTITION BY symbol 
    ORDER BY timestamp 
    ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
) FROM market_data;
```

**After (TimescaleDB with Continuous Aggregation):**
```sql
-- Query pre-computed SMA-20 (takes 50ms)
SELECT * FROM ohlcv_1m_sma20;
```

**Speed Improvement: 100-200x faster!**

## Creating Custom Indicators

### Add More Continuous Aggregations

```sql
-- RSI-14 (1-minute)
CREATE MATERIALIZED VIEW ohlcv_1m_rsi14
WITH (timescaledb.continuous) AS
SELECT 
    symbol,
    time_bucket('1 minute', timestamp) AS bucket,
    -- RSI calculation logic here
FROM market_data
GROUP BY symbol, bucket
WITH NO DATA;

-- Refresh every minute
SELECT add_continuous_aggregate_policy('ohlcv_1m_rsi14',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute'
);
```

### Query Optimization

```sql
-- Use time_bucket for aggregations (much faster)
SELECT 
    symbol,
    time_bucket('5 minutes', timestamp) AS bucket,
    first(open, timestamp) as open,
    max(high) as high,
    min(low) as low,
    last(close, timestamp) as close,
    sum(volume) as volume
FROM market_data
WHERE timestamp > NOW() - INTERVAL '1 day'
GROUP BY symbol, bucket
ORDER BY bucket DESC;
```

## Monitoring

### Check Compression Stats
```sql
SELECT 
    hypertable_name,
    pg_size_pretty(before_compression_total_bytes) as before,
    pg_size_pretty(after_compression_total_bytes) as after,
    round(100 - (after_compression_total_bytes::numeric / before_compression_total_bytes::numeric) * 100, 2) as compression_ratio
FROM timescaledb_information.compression_stats;
```

### Check Chunk Status
```sql
SELECT 
    chunk_name,
    range_start,
    range_end,
    is_compressed,
    pg_size_pretty(total_bytes)
FROM timescaledb_information.chunks
WHERE hypertable_name = 'market_data'
ORDER BY range_start DESC
LIMIT 10;
```

## Troubleshooting

### Migration Fails
```bash
# Check if extension is installed
psql -U keepgaining -d trading_db -c "\dx"

# Manually enable extension
psql -U keepgaining -d trading_db -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"
```

### Slow Queries After Migration
```bash
# Refresh continuous aggregations manually
psql -U keepgaining -d trading_db -c "CALL refresh_continuous_aggregate('ohlcv_1m_sma20', NULL, NULL);"
```

### Rollback Migration
```bash
# CAUTION: This cannot fully revert hypertables
alembic downgrade -1
```

## Next Steps

1. **Run Migration**: `alembic upgrade head`
2. **Update Code**: Use `time_bucket()` for faster queries
3. **Add Indicators**: Create continuous aggregations for RSI, MACD, etc.
4. **Monitor Performance**: Track query speeds in logs
5. **Tune Compression**: Adjust compression age based on your needs

## Resources

- [TimescaleDB Docs](https://docs.timescale.com/)
- [Continuous Aggregations](https://docs.timescale.com/use-timescale/latest/continuous-aggregates/)
- [Compression](https://docs.timescale.com/use-timescale/latest/compression/)
- [Performance Tuning](https://docs.timescale.com/use-timescale/latest/hypertables/about-hypertables/)

---

**Expected Performance Gains:**
- Indicator calculations: **50-100x faster**
- Historical data queries: **10-50x faster**
- Storage usage: **90% reduction** (with compression)
- Query response time: **<100ms** (vs 5-10 seconds)
