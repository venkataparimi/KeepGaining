# F&O Historical Data & Indicators - Complete Guide

## Overview
This guide covers three critical tasks:
1. **Verifying February data completeness** for all stocks
2. **Backfilling historical options data** from January 2023
3. **Computing indicators** for options and futures data

---

## 1. Verify February Data Completeness

### Purpose
Ensure that February data (which can have boundary issues) is correctly downloaded for all stocks across multiple years.

### Script
```powershell
python backend/scripts/verify_february_data.py
```

### What It Checks
- ✅ Number of stocks with February data for each year (2022-2025)
- ✅ Stocks missing February data (but have data in other months)
- ✅ Days within February that have no data (potential gaps)
- ✅ Excludes weekends automatically

### Example Output
```
================================================================================
FEBRUARY DATA COMPLETENESS CHECK
================================================================================

📅 February 2022
--------------------------------------------------------------------------------
Total stocks: 201
Stocks with Feb 2022 data: 195
Stocks missing Feb 2022 data: 6
Missing: GMRINFRA, LARSENTOUB, NATCOPHARMA, PEL, PVR, ZOMATO
✅ No gaps detected in February 2022

📅 February 2023
--------------------------------------------------------------------------------
Total stocks: 201
Stocks with Feb 2023 data: 198
Stocks missing Feb 2023 data: 3
⚠️  Days with no data: 2023-02-15, 2023-02-16
```

### Action Items
- If stocks are missing February data but have data in other months, run:
  ```powershell
  python backend/scripts/backfill_stock_v2.py STOCKNAME 2022 2
  ```

---

## 2. Backfill Historical Options Data from Jan 2023

### Problem
Historical F&O (options and futures) data from January 2023 needs to be backfilled for strategy backtesting.

### Solution
Use `backfill_fo_historical.py` with month-based chunking to avoid date boundary issues.

### Usage Examples

#### Backfill All NIFTY Options from Jan 2023
```powershell
python backend/scripts/backfill_fo_historical.py --underlying NIFTY --year 2023 --month 1
```

#### Backfill Only NIFTY Call Options
```powershell
python backend/scripts/backfill_fo_historical.py --underlying NIFTY --type CE --year 2023 --month 1
```

#### Backfill BANKNIFTY Futures
```powershell
python backend/scripts/backfill_fo_historical.py --underlying BANKNIFTY --type FUTURES --year 2023 --month 1
```

#### Test with Limited Instruments
```powershell
python backend/scripts/backfill_fo_historical.py --underlying NIFTY --limit 10
```

#### Backfill All F&O from Jan 2023 (Warning: This will take hours!)
```powershell
python backend/scripts/backfill_fo_historical.py --year 2023 --month 1
```

### Features
- ✅ **Month-based chunking** - Avoids Feb-Mar overlap issues
- ✅ **Respects expiry dates** - Won't download data beyond option expiry
- ✅ **Filters by underlying** - Process specific stocks/indices
- ✅ **Filters by type** - Process only futures, calls, or puts
- ✅ **Skip existing data** - Won't re-download if data already exists
- ✅ **Rate limiting** - 0.3s delay between requests

### Performance
- **Speed**: ~3-4 instruments per minute (with rate limiting)
- **NIFTY options**: ~500-1000 instruments = 3-5 hours
- **Single underlying**: 30-60 minutes
- **All F&O**: 10-20 hours (not recommended without filtering)

### Recommended Workflow
```powershell
# Step 1: Start with NIFTY (most liquid)
python backend/scripts/backfill_fo_historical.py --underlying NIFTY --year 2023 --month 1

# Step 2: Then BANKNIFTY
python backend/scripts/backfill_fo_historical.py --underlying BANKNIFTY --year 2023 --month 1

# Step 3: Then specific stocks
python backend/scripts/backfill_fo_historical.py --underlying RELIANCE --year 2023 --month 1

# Step 4: Verify
python backend/scripts/check_fo_coverage.py
```

---

## 3. Compute Indicators for Options and Futures

### Purpose
After backfilling F&O data, compute technical indicators (SMA, EMA, RSI, MACD, etc.) for backtesting.

### Script
```powershell
python backend/scripts/compute_fo_indicators.py
```

### Usage Examples

#### Compute Indicators for All NIFTY F&O
```powershell
python backend/scripts/compute_fo_indicators.py --underlying NIFTY
```

#### Compute Indicators for NIFTY Call Options Only
```powershell
python backend/scripts/compute_fo_indicators.py --underlying NIFTY --type CE
```

#### Test with Limited Instruments
```powershell
python backend/scripts/compute_fo_indicators.py --underlying NIFTY --limit 10
```

#### Compute for All F&O (Warning: Very slow!)
```powershell
python backend/scripts/compute_fo_indicators.py
```

### Indicators Computed
- **Moving Averages**: SMA (5, 10, 20, 50, 200), EMA (9, 21, 50, 200)
- **Momentum**: RSI (14)
- **Trend**: MACD, Supertrend, ADX
- **Volatility**: Bollinger Bands, ATR (14)
- **Volume**: VWAP

### Requirements
- Minimum **200 candles** required per instrument
- Instruments with less data are skipped

### Performance
- **Speed**: ~5-10 instruments per minute
- **NIFTY options**: ~500 instruments = 1-2 hours
- **Memory**: ~500MB for large datasets

### Output
Indicators are stored in the `indicator_data` table with columns:
- `instrument_id`, `timestamp`, `timeframe`
- All computed indicator values
- Uses `ON CONFLICT` to update existing records

---

## Complete Workflow Example

### Scenario: Backfill and Compute Indicators for NIFTY Options from Jan 2023

```powershell
# Step 1: Verify current data status
python backend/scripts/check_fo_coverage.py

# Step 2: Backfill NIFTY Call options from Jan 2023
python backend/scripts/backfill_fo_historical.py --underlying NIFTY --type CE --year 2023 --month 1

# Step 3: Backfill NIFTY Put options from Jan 2023
python backend/scripts/backfill_fo_historical.py --underlying NIFTY --type PE --year 2023 --month 1

# Step 4: Verify February data
python backend/scripts/verify_february_data.py

# Step 5: Compute indicators for NIFTY Call options
python backend/scripts/compute_fo_indicators.py --underlying NIFTY --type CE

# Step 6: Compute indicators for NIFTY Put options
python backend/scripts/compute_fo_indicators.py --underlying NIFTY --type PE

# Step 7: Verify indicator data
SELECT 
    im.trading_symbol,
    COUNT(*) as indicator_count,
    MIN(id.timestamp) as earliest,
    MAX(id.timestamp) as latest
FROM indicator_data id
JOIN instrument_master im ON id.instrument_id = im.instrument_id
WHERE im.underlying = 'NIFTY' AND im.instrument_type = 'CE'
GROUP BY im.trading_symbol
ORDER BY im.trading_symbol;
```

---

## Troubleshooting

### February Data Issues
**Problem**: Some stocks missing February data  
**Solution**: Run individual backfill:
```powershell
python backend/scripts/backfill_stock_v2.py STOCKNAME 2022 2
```

### Options Data Not Available
**Problem**: API returns no data for old options  
**Cause**: Option has expired and is beyond the 3-year API limit  
**Solution**: Options data is only available for ~3 years back (2022+)

### Indicator Computation Fails
**Problem**: "Insufficient data" errors  
**Cause**: Less than 200 candles available  
**Solution**: This is normal for recently listed options or those with low liquidity

### Rate Limiting (429 errors)
**Problem**: Too many requests to Upstox API  
**Solution**: Scripts already include rate limiting (0.3-0.5s delays). If still occurring, increase delays in the script.

---

## Data Availability Summary

| Data Type | Available From | Notes |
|-----------|---------------|-------|
| **Equity** | Jan 2022 | Full 1-minute data |
| **Index** | Jan 2022 | Full 1-minute data |
| **F&O (Active)** | Jan 2022 | Current/recent contracts |
| **F&O (Expired)** | Jan 2022 | If within 3-year window |
| **Very Old F&O** | ❌ Not available | Beyond 3-year API limit |

---

## Next Steps

After completing the above:
1. **Generate Parquet datasets** for fast backtesting:
   ```powershell
   python backend/scripts/generate_dataset_incremental.py
   ```

2. **Run backtests** using the strategy engine

3. **Set up daily incremental updates**:
   ```powershell
   schtasks /Create /SC DAILY /TN "DailyFOBackfill" /TR "python C:\code\KeepGaining\backend\scripts\backfill_fo_historical.py --underlying NIFTY --year 2025 --month 1" /ST 18:00
   ```

---

*Last updated: 2025-12-16*
