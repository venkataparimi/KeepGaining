# KeepGaining API & Database Reference

> **IMPORTANT FOR AI AGENTS**: Read this document BEFORE making any API calls or database queries.
> This document contains critical learnings from debugging sessions to prevent repeated mistakes.

---

## Table of Contents
1. [Pre-Flight Checklist](#pre-flight-checklist)
2. [Database Schema](#database-schema)
3. [Database Connection](#database-connection)
4. [Upstox API Reference](#upstox-api-reference)
5. [Common Mistakes & Fixes](#common-mistakes--fixes)
6. [Performance Optimization](#performance-optimization)
7. [Working Code Examples](#working-code-examples)
8. [Debugging Steps](#debugging-steps)

---

## Pre-Flight Checklist

**BEFORE writing any data loading or API code, verify these:**

```sql
-- 1. Check existing data format in the table
SELECT * FROM candle_data LIMIT 5;

-- 2. Check column constraints
SELECT column_name, data_type, character_maximum_length 
FROM information_schema.columns 
WHERE table_name='candle_data';

-- 3. Check primary key constraint
SELECT conname, pg_get_constraintdef(oid) 
FROM pg_constraint 
WHERE conrelid = 'candle_data'::regclass AND contype = 'p';

-- 4. For fast coverage queries, use the summary table
SELECT * FROM candle_data_summary LIMIT 10;
```

---

## Database Schema

### candle_data Table

| Column | Type | Notes |
|--------|------|-------|
| instrument_id | UUID | FK to instrument_master |
| timeframe | varchar(5) | **USE '1m' NOT '1minute'** |
| timestamp | timestamptz | Candle open time |
| open | numeric | |
| high | numeric | |
| low | numeric | |
| close | numeric | |
| volume | bigint | |
| oi | bigint | Open interest |

**Primary Key**: `(instrument_id, timeframe, timestamp)`

### candle_data_summary Materialized View

Pre-aggregated stats for fast queries (33,000x faster than raw table scans):
```sql
SELECT instrument_id, timeframe, first_candle, last_candle, candle_count, first_date, last_date
FROM candle_data_summary;
```

**Refresh after bulk inserts:**
```sql
REFRESH MATERIALIZED VIEW candle_data_summary;
```

### instrument_master Table

| Column | Type | Notes |
|--------|------|-------|
| instrument_id | UUID | Primary key |
| trading_symbol | varchar | e.g., "NIFTY24DEC26000CE" |
| instrument_type | varchar | "EQ", "CE", "PE", "FUTURES", "INDEX" |
| exchange | varchar | "NSE", "BSE" |
| segment | varchar | "NSE_EQ", "NSE_FO", "NSE_INDEX" |
| underlying | varchar | e.g., "NIFTY", "RELIANCE" |
| isin | varchar | For equity instruments |
| lot_size | integer | Contract size |
| tick_size | numeric | Minimum price movement |
| is_active | boolean | Active trading status |

**Note**: The primary key is `instrument_id`, NOT `id`.

---

## Database Connection

**Standard connection string:**
```python
DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'
```

**Connection example:**
```python
import asyncpg
conn = await asyncpg.connect(DB_URL)
```

---

## Upstox API Reference

### Instrument Key Formats

| Segment | Format | Example |
|---------|--------|---------|
| Equity | `NSE_EQ\|<ISIN>` | `NSE_EQ\|INE009A01021` |
| Index | `NSE_INDEX\|<name>` | `NSE_INDEX\|Nifty 50` |
| F&O | `NSE_FO\|<exchange_token>` | `NSE_FO\|49508` |

### Getting Instrument Keys

**Download the master file (required for F&O):**
```python
import gzip
import json
import aiohttp

async def download_master():
    url = 'https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = gzip.decompress(await resp.read())
            instruments = json.loads(data)
            # Returns list of dicts with 'instrument_key', 'exchange_token', etc.
            return instruments
```

**Build a cache for fast lookups:**
```python
# Key by exchange_token for F&O
cache = {int(inst['exchange_token']): inst['instrument_key'] 
         for inst in instruments if 'exchange_token' in inst}
```

### Historical Candle API

**Endpoint (NO AUTH REQUIRED):**
```
GET https://api.upstox.com/v2/historical-candle/{instrument_key}/{interval}/{to_date}/{from_date}
```

**Parameters:**
- `instrument_key`: URL-encoded (e.g., `NSE_FO%7C49508`)
- `interval`: `1minute`, `30minute`, `day`, `week`, `month`
- `to_date`: YYYY-MM-DD (end date)
- `from_date`: YYYY-MM-DD (start date)

**Response:**
```json
{
  "status": "success",
  "data": {
    "candles": [
      ["2024-01-15T09:15:00+05:30", 21500.0, 21510.0, 21490.0, 21505.0, 12345, 5000],
      // [timestamp, open, high, low, close, volume, oi]
    ]
  }
}
```

**Rate Limits:**
- 25 requests/second for historical data
- Use `asyncio.Semaphore(25)` for throttling

---

## Common Mistakes & Fixes

### Mistake 1: Wrong timeframe value
```python
# WRONG - 7 characters, column is varchar(5)
timeframe = '1minute'

# RIGHT
timeframe = '1m'
```

### Mistake 2: Using instrument_id as API key
```python
# WRONG - instrument_id is our internal UUID
url = f".../{instrument_id}/..."

# RIGHT - Use instrument_key from Upstox master file
instrument_key = cache[exchange_token]  # e.g., "NSE_FO|49508"
url = f".../{quote(instrument_key)}/..."
```

### Mistake 3: Temp table with ON COMMIT DELETE ROWS
```python
# WRONG - Data disappears after each statement
await conn.execute('''
    CREATE TEMP TABLE temp_candles (...) ON COMMIT DELETE ROWS
''')

# RIGHT - Use explicit TRUNCATE
await conn.execute('CREATE TEMP TABLE temp_candles (...)')
# ... use table ...
await conn.execute('TRUNCATE temp_candles')
```

### Mistake 4: Missing timeframe in INSERT
```python
# WRONG - Missing column that's part of primary key
INSERT INTO candle_data (instrument_id, timestamp, ...) VALUES (...)
ON CONFLICT (instrument_id, timestamp) DO UPDATE  # Error!

# RIGHT - Include all PK columns
INSERT INTO candle_data (instrument_id, timeframe, timestamp, ...) VALUES (...)
ON CONFLICT (instrument_id, timeframe, timestamp) DO UPDATE ...
```

### Mistake 5: Slow count distinct queries
```python
# WRONG - Takes 7+ minutes on 363M rows
SELECT count(DISTINCT instrument_id) FROM candle_data

# RIGHT - Use the materialized summary view
SELECT count(*) FROM candle_data_summary
```

---

## Performance Optimization

### Existing Indexes

| Index | Columns | Use Case |
|-------|---------|----------|
| pk_candle_data | (instrument_id, timeframe, timestamp) | Point lookups, upserts |
| idx_candle_instrument_time | (instrument_id, timestamp) | Single instrument queries |
| idx_candle_time | (timestamp) | Time range scans |

### Summary View (candle_data_summary)

Pre-computed aggregates for each instrument:
- first_candle, last_candle
- candle_count
- first_date, last_date

**Query time comparison:**
- Raw table: 431 seconds
- Summary view: 0.013 seconds (33,000x faster)

**Remember to refresh after bulk inserts:**
```python
await conn.execute('REFRESH MATERIALIZED VIEW candle_data_summary')
```

---

## Working Code Examples

### Download and Save Candles
```python
import asyncio
import aiohttp
import asyncpg
from urllib.parse import quote
from datetime import datetime

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'

async def download_candles(instrument_key: str, from_date: str, to_date: str) -> list:
    """Download candles from Upstox API."""
    encoded_key = quote(instrument_key, safe='')
    url = f"https://api.upstox.com/v2/historical-candle/{encoded_key}/1minute/{to_date}/{from_date}"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                return data.get('data', {}).get('candles', [])
    return []

async def save_candles(conn, instrument_id: str, candles: list):
    """Save candles to database. ALWAYS use '1m' for timeframe."""
    for candle in candles:
        ts_str, o, h, l, c, vol, oi = candle
        ts = datetime.fromisoformat(ts_str.replace('+05:30', '+05:30'))
        
        await conn.execute('''
            INSERT INTO candle_data 
                (instrument_id, timeframe, timestamp, open, high, low, close, volume, oi)
            VALUES ($1, '1m', $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (instrument_id, timeframe, timestamp) DO UPDATE SET
                open = EXCLUDED.open, 
                high = EXCLUDED.high, 
                low = EXCLUDED.low,
                close = EXCLUDED.close, 
                volume = EXCLUDED.volume, 
                oi = EXCLUDED.oi
        ''', instrument_id, ts, o, h, l, c, vol, oi or 0)
```

### Query Instrument Coverage (Fast)
```python
async def get_instruments_needing_backfill(conn, days_threshold: int = 5):
    """Find instruments that haven't been updated recently."""
    return await conn.fetch('''
        SELECT s.instrument_id, s.last_date, s.candle_count,
               m.trading_symbol, m.instrument_type, m.exchange_token
        FROM candle_data_summary s
        JOIN instrument_master m ON s.instrument_id = m.id
        WHERE s.last_date < CURRENT_DATE - $1
    ''', days_threshold)

async def get_fo_without_data(conn):
    """Find F&O instruments with no candle data."""
    return await conn.fetch('''
        SELECT id, trading_symbol, exchange_token, expiry
        FROM instrument_master m
        WHERE instrument_type IN ('CE', 'PE', 'FUTURES')
        AND NOT EXISTS (
            SELECT 1 FROM candle_data_summary s WHERE s.instrument_id = m.id
        )
    ''')
```

---

## Debugging Steps

### Before Writing Code
1. **Read this document**
2. Check schema: `SELECT * FROM candle_data LIMIT 1`
3. Check constraints: `\d candle_data` or information_schema query
4. Test with 1 instrument first

### When API Returns Empty/Errors
1. Verify instrument_key format matches segment (EQ vs FO vs INDEX)
2. URL-encode the instrument_key (pipe `|` → `%7C`)
3. Check date format is YYYY-MM-DD
4. Verify instrument exists in Upstox master file

### When INSERT Fails
1. Check all PK columns are included (instrument_id, timeframe, timestamp)
2. Verify timeframe is '1m' (max 5 chars)
3. Check for type mismatches (timestamp format, numeric vs int)

### When Queries Are Slow
1. Use candle_data_summary for aggregate queries
2. Check EXPLAIN ANALYZE output
3. Ensure queries filter on indexed columns (instrument_id, timestamp)

---

## Database Indexes Reference

### candle_data (97 GB, 363M+ rows)
| Index | Columns | Purpose |
|-------|---------|---------|
| pk_candle_data | (instrument_id, timeframe, timestamp) | Primary key, upserts |
| idx_candle_instrument_time | (instrument_id, timestamp) | Single instrument queries |
| idx_candle_time | (timestamp) | Time range scans |

### candle_data_summary (Materialized View, 6.6 MB)
| Index | Columns | Purpose |
|-------|---------|---------|
| idx_summary_instrument | (instrument_id) | Fast instrument lookup |
| idx_summary_last_date | (last_date) | Find stale data |

**Refresh after bulk inserts:**
```sql
REFRESH MATERIALIZED VIEW candle_data_summary;
```

### instrument_master (19 MB)
| Index | Columns | Purpose |
|-------|---------|---------|
| pk_instrument_master | (instrument_id) | Primary key |
| uq_instrument_symbol_exchange | (trading_symbol, exchange) | Unique constraint |
| idx_instrument_active | (is_active) | Filter active instruments |
| idx_instrument_type | (instrument_type) | Filter CE/PE/FUTURES/EQ |
| idx_instrument_underlying | (underlying) | Filter by underlying |
| idx_im_trading_symbol | (trading_symbol) | Symbol lookups |
| idx_im_segment | (segment) | Filter by segment |
| idx_im_type_underlying | (instrument_type, underlying) | Combined filter |

### option_master
| Index | Columns | Purpose |
|-------|---------|---------|
| pk_option_master | (option_id) | Primary key |
| idx_option_composite | (underlying_instrument_id, expiry_date, option_type) | Chain lookup |
| idx_om_expiry_date | (expiry_date) | Filter by expiry |
| idx_om_strike_price | (strike_price) | Filter by strike |
| idx_om_underlying_inst | (underlying_instrument_id) | Filter by underlying |
| idx_om_option_type | (option_type) | Filter CE/PE |
| idx_om_underlying_expiry | (underlying_instrument_id, expiry_date) | Options chain |
| idx_om_underlying_expiry_strike | (underlying_instrument_id, expiry_date, strike_price) | Full chain |

### future_master
| Index | Columns | Purpose |
|-------|---------|---------|
| pk_future_master | (future_id) | Primary key |
| idx_fm_expiry_date | (expiry_date) | Filter by expiry |
| idx_fm_underlying_inst | (underlying_instrument_id) | Filter by underlying |

### indicator_data
| Index | Columns | Purpose |
|-------|---------|---------|
| pk_indicator_data | (instrument_id, timeframe, timestamp) | Primary key |
| idx_indicator_time | (timestamp) | Time range queries |
| idx_ind_instrument_time | (instrument_id, timestamp) | Instrument time series |

### orders
| Index | Columns | Purpose |
|-------|---------|---------|
| pk_orders | (order_id) | Primary key |
| idx_order_status | (status) | Filter by status |
| idx_order_created | (created_at) | Sort by time |
| idx_order_strategy | (strategy_id) | Filter by strategy |
| idx_order_instrument | (instrument_id) | Filter by instrument |
| idx_order_broker | (broker_name) | Filter by broker |
| idx_ord_status | (status) | Filter pending/filled |
| idx_ord_created | (created_at) | Recent orders |
| idx_ord_strategy | (strategy_id) | Strategy orders |

### trades
| Index | Columns | Purpose |
|-------|---------|---------|
| pk_trades | (trade_id) | Primary key |
| idx_trade_executed | (executed_at) | Time range queries |
| idx_trade_strategy | (strategy_id) | Filter by strategy |
| idx_trade_order | (order_id) | Link to order |
| idx_trade_instrument | (instrument_id) | Filter by instrument |
| idx_trd_executed_at | (executed_at) | Sort by execution time |
| idx_trd_strategy | (strategy_id) | Strategy trades |

### positions
| Index | Columns | Purpose |
|-------|---------|---------|
| pk_positions | (position_id) | Primary key |
| idx_position_status | (status) | Open/closed filter |
| idx_position_strategy | (strategy_id) | Filter by strategy |
| idx_position_instrument | (instrument_id) | Filter by instrument |
| idx_pos_instrument | (instrument_id) | Position lookup |
| idx_pos_strategy | (strategy_id) | Strategy positions |

### signal_log
| Index | Columns | Purpose |
|-------|---------|---------|
| pk_signal_log | (signal_id) | Primary key |
| idx_signal_time | (generated_at) | Time range queries |
| idx_signal_strategy | (strategy_id) | Filter by strategy |
| idx_signal_type | (signal_type) | Filter by signal type |
| idx_sig_generated_at | (generated_at) | Recent signals |
| idx_sig_strategy | (strategy_id) | Strategy signals |

### option_chain_snapshot
| Index | Columns | Purpose |
|-------|---------|---------|
| pk_option_chain_snapshot | (snapshot_id) | Primary key |
| idx_chain_time | (timestamp) | Time range queries |
| idx_chain_underlying | (underlying_instrument_id) | Filter by underlying |
| idx_chain_expiry | (expiry_date) | Filter by expiry |
| idx_ocs_timestamp | (timestamp) | Time series |
| idx_ocs_underlying_inst | (underlying_instrument_id) | Underlying lookup |
| idx_ocs_expiry_date | (expiry_date) | Expiry filter |

### option_greeks
| Index | Columns | Purpose |
|-------|---------|---------|
| pk_option_greeks | (option_id, timestamp) | Primary key |
| idx_greeks_time | (timestamp) | Time range queries |
| idx_og_option_time | (option_id, timestamp) | Greeks time series |

### expiry_calendar
| Index | Columns | Purpose |
|-------|---------|---------|
| pk_expiry_calendar | (expiry_id) | Primary key |
| idx_expiry_date | (expiry_date) | Find expiries |
| idx_expiry_underlying | (underlying) | Filter by underlying |
| idx_ec_expiry_date | (expiry_date) | Expiry lookup |
| idx_ec_underlying | (underlying) | Underlying filter |

### daily_pnl
| Index | Columns | Purpose |
|-------|---------|---------|
| pk_daily_pnl | (pnl_id) | Primary key |
| idx_pnl_date | (date) | Filter by date |
| idx_pnl_strategy | (strategy_id) | Filter by strategy |

---

## File Locations

| File | Purpose |
|------|---------|
| `backend/scripts/UPSTOX_API_REFERENCE.md` | This reference document |
| `backend/scripts/backfill_all_data.py` | Comprehensive backfill script |
| `backend/scripts/check_data_gaps_v2.py` | Gap analysis |
| `backend/scripts/optimize_indexes.py` | Index and view creation |
| `backend/scripts/test_query_perf.py` | Query performance testing |

---

## Version History

| Date | Change |
|------|--------|
| 2025-12-02 | Initial version after debugging session |
| 2025-12-02 | Added candle_data_summary materialized view (33,000x faster queries) |
| 2025-12-02 | Comprehensive rewrite with all learnings |
| 2025-12-02 | Added complete database index reference for all tables |
