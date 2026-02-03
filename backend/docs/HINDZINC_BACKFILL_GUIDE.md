# HINDZINC Options Data Backfill Guide

## 🎯 Objective
Backfill HINDZINC options data for December 2025 to analyze the Dec 1 trade

## 📊 Current Status

### ✅ What We Have:
- HINDZINC Futures data (98,955 candles)
- Date range: March 28 - Dec 15, 2025
- December 1, 2025 futures data available

### ❌ What's Missing:
- HINDZINC Options (CE/PE) in instrument_master
- HINDZINC Options candle data
- Specifically: 500 CE for Dec 1, 2025

---

## 🚀 Backfill Steps

### Step 1: Run Existing Backfill Script

The easiest way is to use your existing comprehensive backfill script:

```bash
# Navigate to scripts directory
cd backend/scripts

# Run backfill for current expiry (includes options)
python backfill_all_data.py --mode current

# Or run full backfill (takes longer but gets everything)
python backfill_all_data.py --mode all
```

This will:
1. Update instrument_master with current options
2. Download options candle data
3. Include HINDZINC 500 CE if it exists

### Step 2: Verify Data

After backfill, run:
```bash
python check_hindzinc_options.py
```

This will confirm:
- ✓ HINDZINC options in instrument_master
- ✓ Candle data for Dec 1, 2025
- ✓ 500 CE specifically

---

## 🔍 Alternative: Manual Backfill

If the automated script doesn't work, here's the manual process:

### 1. Check Your Data Provider

You're using one of these:
- Shoonya (Finvasia)
- Dhan
- Zerodha
- Other

### 2. API Endpoints Needed

```python
# Get instrument list (includes options)
GET /instruments

# Get historical candle data
GET /historical/{instrument_id}?from=2025-12-01&to=2025-12-01&interval=1minute
```

### 3. Specific Requirements

For HINDZINC 500 CE on Dec 1, 2025:
- Symbol: HINDZINC
- Strike: 500
- Type: CE
- Expiry: Nearest weekly/monthly expiry after Dec 1
- Date: 2025-12-01
- Interval: 1-minute candles

---

## 💡 Quick Test

To test if backfill is working, run:

```bash
# Check current data status
python backend/scripts/check_hindzinc_options.py

# Run backfill
python backend/scripts/backfill_all_data.py --mode current

# Check again
python backend/scripts/check_hindzinc_options.py
```

---

## 📝 What Happens After Backfill

Once we have the data, I'll:

1. ✅ **Analyze Dec 1 Trade**
   - See actual 500 CE premium movement
   - Verify ₹14 → ₹23 movement
   - Identify exact entry/exit times

2. ✅ **Reverse-Engineer Strategy**
   - Find what triggered the entry
   - Determine exit rules
   - Identify the pattern

3. ✅ **Backtest the Strategy**
   - Test on Oct-Dec 2025
   - Calculate win rate, P&L
   - Compare with Morning Momentum Alpha

4. ✅ **Deploy Strategy #2**
   - Add to dashboard
   - Create live scanner
   - Enable paper/live trading

---

## 🎯 Expected Timeline

- **Backfill**: 10-30 minutes (depending on data volume)
- **Analysis**: 5 minutes
- **Strategy Development**: 30 minutes
- **Backtesting**: 1-2 hours
- **Total**: ~2-3 hours to complete strategy

---

## 🚨 If Backfill Fails

Common issues and solutions:

### Issue 1: No Options in Instrument Master
**Solution**: Update instrument master first
```bash
# This should be part of backfill_all_data.py
# But if needed separately, check for update_instruments script
```

### Issue 2: API Rate Limits
**Solution**: The backfill script has rate limiting built-in
- Waits between requests
- Retries on failure
- Logs progress

### Issue 3: Missing Expiry Data
**Solution**: Check expiry calendar
```sql
SELECT * FROM expiry_calendar 
WHERE underlying = 'HINDZINC' 
AND expiry_date >= '2025-12-01'
ORDER BY expiry_date;
```

---

## 📊 Next Command to Run

```bash
# Start the backfill process
python backend/scripts/backfill_all_data.py --mode current
```

This will get us the HINDZINC options data we need!

---

*Once backfill completes, we can immediately analyze the Dec 1 trade and build your strategy!* 🚀
