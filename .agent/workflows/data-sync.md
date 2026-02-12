---
description: Guidelines for data synchronization and backfill operations
---

# Data Sync Best Practices

## Core Principles

1. **ALWAYS check database first** before downloading:
   - Query existing data in DB to determine what's already synced
   - Update `sync_status.json` with existing data before downloading
   - Prevents redundant API calls and re-downloading same data

2. **Use sync_status.json for tracking**:
   - Located at: `backend/scripts/data/sync_status.json`
   - Track per-segment sync status with timestamps
   - Track per-expiry sync for F&O options in `synced_expiries` field

3. **Leverage existing scripts** - DO NOT create new ones:
   - `daily_sync.py` - Main sync orchestrator with segments
   - `backfill_expired_data.py` - Expired F&O options API calls
   - `backfill_all_data.py` - Historical gap filling

## Available Sync Segments

| Segment | Description | Script |
|---------|-------------|--------|
| `equity` | F&O eligible stocks | daily_sync.py |
| `indices_nse` | NSE indices | daily_sync.py |
| `indices_bse` | BSE indices | daily_sync.py |
| `fo_current` | Current F&O contracts | daily_sync.py |
| `fo_historical` | Historical gaps for active F&O | daily_sync.py |
| `fo_expired` | Expired weekly options | daily_sync.py |
| `indicators` | Technical indicators | daily_sync.py |

## Database Schema Notes

- `instrument_master`: Base instrument records (no expiry/strike)
- `option_master`: Option-specific data (strike, expiry, lot_size)
- `candle_data`: OHLCV data with ON CONFLICT DO UPDATE

## Before Any Sync Operation

```python
# 1. Query existing data first
existing = await conn.fetch('''
    SELECT DISTINCT underlying, expiry_date
    FROM option_master om
    JOIN instrument_master im ON om.instrument_id = im.instrument_id
    WHERE expiry_date < CURRENT_DATE
''')

# 2. Update tracking before download
for row in existing:
    synced_expiries[row['underlying']].append(str(row['expiry_date']))
save_config(config)

# 3. Only download what's missing
new_to_sync = [e for e in available if e not in synced_expiries]
```

## Commands

```bash
# Check current sync status
python scripts/daily_sync.py --status

# Sync specific segment
python scripts/daily_sync.py --segment fo_expired

# Force re-sync (ignores stale check)
python scripts/daily_sync.py --segment fo_expired --force

# Dry run
python scripts/daily_sync.py --segment fo_expired --dry-run
```

## Upstox API Keys for Indices

| Symbol | Upstox Instrument Key |
|--------|----------------------|
| NIFTY | `NSE_INDEX\|Nifty 50` |
| BANKNIFTY | `NSE_INDEX\|Nifty Bank` |
| FINNIFTY | `NSE_INDEX\|Nifty Fin Service` |
| SENSEX | `BSE_INDEX\|SENSEX` |
| BANKEX | `BSE_INDEX\|BANKEX` |

## Critical Reminders

- **lot_size** is NOT NULL in `option_master` - always provide a default
- Expired options API returns `minimum_lot` not `lot_size`
- Always use `ON CONFLICT DO UPDATE` for candle inserts
- Save sync progress after EACH expiry for crash recovery

---

# Indicator Computation Pipeline

## Overview

3-stage pipeline for computing and storing technical indicators:

```
DB Candles → Stage 1 → .pkl files → Stage 2 → .parquet files → Stage 3 → DB indicator_data
```

## Stage 1: Compute Indicators

**Script:** `backend/scripts/pipeline/stage1_compute.py`

**What it does:**
- Fetches candle data from `candle_data` table
- Computes all technical indicators using optimized numpy
- Outputs `.pkl` files to `data/computed/`

**Indicators computed:**
- SMA (9, 20, 50, 200)
- EMA (9, 21, 50, 200)
- RSI (14)
- MACD (12/26/9)
- Bollinger Bands (20, 2σ)
- ATR (14)
- ADX (+DI, -DI)
- Supertrend (10, 3x)
- OBV
- VWAP (daily reset)
- Pivot Points (Daily)
- Fibonacci Levels

**Commands:**
```bash
# Compute with 8 parallel workers
python scripts/pipeline/stage1_compute.py --workers 8

# Limit to specific instrument type
python scripts/pipeline/stage1_compute.py --type EQUITY

# Resume from last position (default)
python scripts/pipeline/stage1_compute.py --no-resume  # Start fresh
```

**Progress tracking:** `data/compute_progress.json`

## Stage 2: Convert to Parquet

**Script:** `backend/scripts/pipeline/stage2_parquet.py`

**What it does:**
- Watches `data/computed/` for new `.pkl` files
- Converts to optimized Parquet format
- Outputs to `data/indicators/`
- Deletes `.pkl` after successful conversion

**Commands:**
```bash
# Convert all pending files
python scripts/pipeline/stage2_parquet.py

# Watch mode (continuous)
python scripts/pipeline/stage2_parquet.py --watch --interval 5
```

**Progress tracking:** `data/parquet_progress.json`

## Stage 3: Load to Database

**Script:** `backend/scripts/pipeline/stage3_db_load.py`

**What it does:**
- Reads Parquet files from `data/indicators/`
- Bulk inserts into `indicator_data` table
- Moves processed files to `data/loaded/`

**Commands:**
```bash
# Load all Parquet files
python scripts/pipeline/stage3_db_load.py

# Keep files after loading (don't move)
python scripts/pipeline/stage3_db_load.py --no-move
```

**Progress tracking:** `data/db_load_progress.json`

## Running the Full Pipeline

Run stages in parallel (recommended):

```bash
# Terminal 1: Compute
python scripts/pipeline/stage1_compute.py --workers 8

# Terminal 2: Convert (watch mode)
python scripts/pipeline/stage2_parquet.py --watch

# Terminal 3: Load to DB
python scripts/pipeline/stage3_db_load.py
```

Or sequentially for simpler runs:
```bash
python scripts/pipeline/stage1_compute.py
python scripts/pipeline/stage2_parquet.py
python scripts/pipeline/stage3_db_load.py
```

## Via daily_sync.py

For incremental indicator updates:
```bash
python scripts/daily_sync.py --segment indicators
```

## Data Directories

| Directory | Purpose |
|-----------|---------|
| `data/computed/` | Stage 1 output (.pkl) |
| `data/indicators/` | Stage 2 output (.parquet) |
| `data/loaded/` | Processed Parquet files |

## Database Table: indicator_data

Key columns:
- `instrument_id` (FK to instrument_master)
- `timeframe` (1m, 5m, 1h, 1d)
- `timestamp`
- All indicator columns (sma_9, rsi_14, etc.)

Primary key: `(instrument_id, timeframe, timestamp)`
