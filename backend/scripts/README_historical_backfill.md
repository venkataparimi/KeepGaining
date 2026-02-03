# Historical Data Backfill from January 2022

## Overview
This document explains how to backfill historical stock data from January 2022 using the improved backfill scripts that avoid the Feb-March overlap issue.

## Problem Identified
- The original backfill script used 30-day chunks which could cause issues when date ranges overlapped month boundaries (especially Feb-Mar)
- Upstox API supports historical data back to approximately **January 2022** (3 years)
- Data before 2021 returns 0 candles

## Solution
Created `backfill_stock_v2.py` which:
- Uses **calendar month-based chunking** instead of fixed 30-day periods
- Respects month boundaries to avoid Feb-Mar overlap issues
- Starts from the 1st day of the month and ends on the last day
- Supports custom start year and month

## Usage

### Backfill from January 2022 (default)
```powershell
python backend/scripts/backfill_stock_v2.py IEX
```

### Backfill from a specific date
```powershell
# Format: python backfill_stock_v2.py SYMBOL YEAR MONTH
python backend/scripts/backfill_stock_v2.py RELIANCE 2022 1
python backend/scripts/backfill_stock_v2.py TATASTEEL 2023 6
```

### Backfill multiple stocks
```powershell
# Create a batch file
foreach ($stock in @('IEX', 'RELIANCE', 'TCS', 'INFY')) {
    python backend/scripts/backfill_stock_v2.py $stock 2022 1
}
```

## Features

### Month-Based Chunking
- Downloads data month by month (Jan 1-31, Feb 1-28/29, etc.)
- Avoids partial month issues
- Handles leap years correctly
- No overlap between chunks

### Progress Tracking
- Shows month name and date range for each chunk
- Displays candle count for each month
- Total summary at the end

### Error Handling
- Skips months with no data (e.g., before 2022)
- Handles API errors gracefully
- Uses ON CONFLICT to avoid duplicates
- Continues even if materialized view refresh fails

## Example Output
```
=== Backfilling IEX from 2022-01 ===
Found: IEX | Key: NSE_EQ|INE022Q01020
Existing data: 2024-10-22 to 2025-12-15 (99,495 candles)
Downloading from 2022-01-01 to 2025-12-16

  Jan 2022     (2022-01-01 to 2022-01-31)... 7,500 candles
  Feb 2022     (2022-02-01 to 2022-02-28)... 7,500 candles
  Mar 2022     (2022-03-01 to 2022-03-31)... 8,250 candles
  ...
  Dec 2025     (2025-12-01 to 2025-12-16)... 4,125 candles

✅ Total: 245,000 candles across 47 months
✅ Refreshed candle_data_summary
```

## Data Availability

| Time Period | Status | Notes |
|-------------|--------|-------|
| **2022-01 onwards** | ✅ Available | Full 1-minute candle data |
| **2021 and earlier** | ❌ Not available | API returns 0 candles |
| **Current month** | ✅ Partial | Up to current date |

## Troubleshooting

### "No data" for recent months
- Check if the stock was listed/trading during that period
- Verify the stock symbol is correct
- Some stocks may have gaps in historical data

### API 400 errors
- Token may have expired - run `python backend/scripts/refresh_upstox_token.py`
- Rate limiting - the script includes 0.5s delays between requests

### Materialized view refresh fails
- This is non-critical - the data is still saved
- You can manually refresh later with:
  ```sql
  REFRESH MATERIALIZED VIEW candle_data_summary;
  ```

## Performance
- **Speed**: ~1-2 months per second (with rate limiting)
- **Duration**: ~30-40 seconds for 3 years of data
- **Data size**: ~250,000 candles for 3 years (1-minute data)

## Next Steps
After backfilling:
1. Run the incremental dataset generator to create Parquet files:
   ```powershell
   python backend/scripts/generate_dataset_incremental.py --symbol IEX
   ```

2. Verify the data:
   ```powershell
   python backend/scripts/check_iex_stock.py
   ```

---
*Last updated: 2025-12-16*
