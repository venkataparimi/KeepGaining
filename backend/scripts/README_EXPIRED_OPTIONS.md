# Backfilling Expired Options - Complete Guide

## Problem Identified

When trying to backfill **expired options** (e.g., NIFTY 14000 CE 26 DEC 24), the regular historical candle API fails with "No key" error because:

1. **Expired options use a DIFFERENT API** - Upstox Expired Instruments API
2. **Different instrument key format** - Expired instruments have their own key structure
3. **Cannot use regular instrument master** - Need to query expired contracts separately

## Solution: Use Upstox Expired Instruments API

### API Endpoints

| Purpose | Endpoint | Method |
|---------|----------|--------|
| List expired expiries | `/v2/expired-instruments/expiries` | GET |
| Get expired option contracts | `/v2/expired-instruments/option/contract` | GET |
| Get expired futures contracts | `/v2/expired-instruments/future/contract` | GET |
| Download expired historical data | `/v2/expired-instruments/historical-candle/{expired_instrument_key}/...` | GET |

## Usage

### Step 1: Refresh Your Token (IMPORTANT!)
```powershell
python backend/scripts/refresh_upstox_token.py
```
**Note**: Tokens expire after 24 hours. Always refresh before using expired instruments API.

### Step 2: List Available Expired Expiries
```powershell
# List all available expired expiries for NIFTY
python backend/scripts/backfill_expired_options.py --symbol NIFTY

# List for BANKNIFTY
python backend/scripts/backfill_expired_options.py --symbol BANKNIFTY
```

### Step 3: Backfill Specific Expiry
```powershell
# Backfill NIFTY Call options for Dec 26, 2024 expiry
python backend/scripts/backfill_expired_options.py --symbol NIFTY --expiry 2024-12-26 --type CE

# Backfill NIFTY Put options for Dec 26, 2024
python backend/scripts/backfill_expired_options.py --symbol NIFTY --expiry 2024-12-26 --type PE

# Test with limited contracts
python backend/scripts/backfill_expired_options.py --symbol NIFTY --expiry 2024-12-26 --type CE --limit 5
```

### Step 4: Backfill Multiple Expiries
```powershell
# Create a batch script
$expiries = @('2024-12-26', '2024-11-28', '2024-10-31')
foreach ($exp in $expiries) {
    python backend/scripts/backfill_expired_options.py --symbol NIFTY --expiry $exp --type CE
    python backend/scripts/backfill_expired_options.py --symbol NIFTY --expiry $exp --type PE
}
```

## Important Notes

### 1. Token Expiration
- Upstox tokens expire after **24 hours**
- Always run `refresh_upstox_token.py` before starting
- If you get 401 errors, your token has expired

### 2. API Limitations
- Expired Instruments API may have different rate limits
- Use 0.3s delays between requests (built into script)
- May require special API permissions (check with Upstox)

### 3. Data Availability
- Expired instruments API typically has data for **recently expired** contracts
- Very old contracts (>1 year) may not be available
- Test with recent expiries first (e.g., Dec 2024, Nov 2024)

### 4. Instrument Matching
- Script matches expired contracts to `instrument_master` by `trading_symbol`
- If symbol not found in DB, it will be skipped
- Ensure your `instrument_master` is up to date

## Workflow for Historical Options (Jan 2023)

### Option A: Use Expired Instruments API (Recommended for recent expiries)
```powershell
# 1. Refresh token
python backend/scripts/refresh_upstox_token.py

# 2. List available expiries
python backend/scripts/backfill_expired_options.py --symbol NIFTY

# 3. Backfill each expiry from 2023
python backend/scripts/backfill_expired_options.py --symbol NIFTY --expiry 2023-01-26 --type CE
python backend/scripts/backfill_expired_options.py --symbol NIFTY --expiry 2023-01-26 --type PE
# ... repeat for other expiries
```

### Option B: Use Regular API for Active Contracts
For contracts that are **still active** or **recently expired** (within ~3 months):
```powershell
python backend/scripts/backfill_fo_historical.py --underlying NIFTY --year 2024 --month 10
```

### Option C: Hybrid Approach (Best)
1. Use **regular API** for active and recently expired contracts (last 3 months)
2. Use **expired instruments API** for older expired contracts (3+ months old)

## Troubleshooting

### Error: "Invalid token used to access API" (401)
**Solution**: Refresh your token
```powershell
python backend/scripts/refresh_upstox_token.py
```

### Error: "No contracts found"
**Possible causes**:
1. Expiry date format incorrect (must be YYYY-MM-DD)
2. No contracts available for that expiry
3. Symbol name incorrect (use 'NIFTY', not 'NIFTY 50')

### Error: "Not in DB"
**Cause**: Trading symbol not found in `instrument_master`  
**Solution**: Update instrument master or the symbol has a different name

### No Data Downloaded
**Possible causes**:
1. Expired instruments API requires special permissions
2. Data not available for that time period
3. Rate limiting - try adding longer delays

## Example Output

```
=== Backfilling Expired NIFTY CE Options ===

Fetching available expired expiries...
Available expiries: 2024-12-26, 2024-11-28, 2024-10-31, 2024-09-26, ...
Total: 24 expiries

Re-run with --expiry YYYY-MM-DD to backfill specific expiry
```

```
=== Backfilling Expired NIFTY CE Options ===

Fetching CE contracts for expiry: 2024-12-26
Found 50 contracts

[1/50] NIFTY 24000 CE 26 DEC 24                 | ✅ 8,250 candles
[2/50] NIFTY 24100 CE 26 DEC 24                 | ✅ 8,100 candles
[3/50] NIFTY 24200 CE 26 DEC 24                 | ✅ 7,950 candles
...

✅ Processed 48/50 contracts
✅ Total candles: 385,000
```

## Scripts Summary

| Script | Purpose | When to Use |
|--------|---------|-------------|
| `backfill_expired_options.py` | Expired F&O via Expired API | For contracts expired >3 months ago |
| `backfill_fo_historical.py` | Active/recent F&O via regular API | For active or recently expired (<3 months) |
| `backfill_stock_v2.py` | Equity historical data | For stock data from Jan 2022 |

## Next Steps

1. **Refresh token**:
   ```powershell
   python backend/scripts/refresh_upstox_token.py
   ```

2. **Test with recent expiry**:
   ```powershell
   python backend/scripts/backfill_expired_options.py --symbol NIFTY --expiry 2024-12-26 --type CE --limit 5
   ```

3. **If successful, backfill more**:
   ```powershell
   python backend/scripts/backfill_expired_options.py --symbol NIFTY --expiry 2024-12-26 --type CE
   ```

4. **Compute indicators**:
   ```powershell
   python backend/scripts/compute_fo_indicators.py --underlying NIFTY --type CE
   ```

---

*Last updated: 2025-12-16*
