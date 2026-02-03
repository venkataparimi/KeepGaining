# Trade Log & Journal - Complete Guide

## 📊 Where to See Your Trades

### **New Page Created**: Trade Log
**URL**: `http://localhost:3001/trades`
**Navigation**: Sidebar → "Trade Log" (📋 List icon)

---

## ✨ Features

### 1. **Complete Trade History**
View all trades from:
- ✅ **Backtest** (Historical simulation)
- ✅ **Paper Trading** (Simulated live)
- ✅ **Live Trading** (Real money)

### 2. **Powerful Filters**
- **Trade Type**: All / Backtest / Paper / Live
- **Month**: October / November / December 2025
- **Search**: Filter by stock name

### 3. **Summary Statistics**
- Total Trades
- Wins / Losses
- Win Rate %
- Total P&L

### 4. **Detailed Trade Table**
Each trade shows:
- Date
- Stock Symbol
- Strike & Option Type (CE/PE)
- Entry Time & Premium
- Exit Time & Premium
- P&L Percentage
- P&L Amount (₹)
- Exit Reason (Target/Stop/Time)
- Trade Type Badge

### 5. **Export Functionality**
- **Download CSV** button
- Exports filtered trades
- Includes all trade details
- Filename: `morning-momentum-alpha-trades-YYYY-MM-DD.csv`

---

## 🔄 Data Sources

### Current Implementation:
The Trade Log page loads data from:
1. **API Endpoint**: `http://localhost:8000/api/strategy/trades`
2. **CSV Files**: `backtest_exit_*.csv` (your generated backtest results)

### Files Location:
```
c:/code/KeepGaining/
├── backtest_exit_1430_1765989303.csv  (October data)
├── backtest_exit_1430_1765987831.csv  (November data)
├── backtest_exit_1430_1765988429.csv  (December data)
```

---

## 📝 Trade Data Structure

Each trade record contains:
```json
{
  "date": "2025-12-02",
  "stock": "RELIANCE",
  "strike": 1300,
  "option_type": "CE",
  "entry_time": "2025-12-02T09:30:00",
  "entry_premium": 45.50,
  "exit_time": "2025-12-02T11:45:00",
  "exit_premium": 68.25,
  "option_pnl_pct": 50.0,
  "option_pnl_amount": 11375,
  "exit_reason": "Target (50%)",
  "trade_type": "backtest"
}
```

---

## 🚀 To View Your Trades

### Option 1: Via Frontend (Recommended)
1. Navigate to `http://localhost:3001/trades`
2. Use filters to narrow down trades
3. Click "Export CSV" to download

### Option 2: Via API
```bash
# Get all trades
curl http://localhost:8000/api/strategy/trades

# Get trades for specific month
curl http://localhost:8000/api/strategy/trades?month=2025-11

# Get trades for specific date
curl http://localhost:8000/api/strategy/trades?date=2025-12-02

# Limit results
curl http://localhost:8000/api/strategy/trades?limit=50
```

### Option 3: Direct CSV
Open any of the `backtest_exit_*.csv` files in Excel or Google Sheets

---

## 📊 Trade Statistics Available

### Overall (Oct-Dec 2025):
- **Total Trades**: 473
- **Win Rate**: 81.6%
- **Total P&L**: ₹12.21 Lakhs

### By Month:
| Month | Trades | Win Rate | P&L |
|-------|--------|----------|-----|
| October | 82 | 84.1% | ₹2.19L |
| November | 311 | 80.1% | ₹7.86L |
| December | 80 | 85.0% | ₹2.16L |

---

## 🎨 UI Features

### Color Coding:
- 🟢 **Green**: Winning trades, positive P&L
- 🔴 **Red**: Losing trades, negative P&L
- 🔵 **Blue**: Backtest trades
- 🟡 **Yellow**: Paper trades
- 🟢 **Green**: Live trades

### Badges:
- 📊 **Backtest**: Historical simulation
- 📝 **Paper**: Simulated live trading
- 🔴 **Live**: Real money trades

### Icons:
- ↗️ **Trending Up**: Winning trade
- ↘️ **Trending Down**: Losing trade
- ✅ **Check**: Call option (CE)
- ⭕ **Circle**: Put option (PE)

---

## 🔮 Future Enhancements

1. **Real-time Updates**: WebSocket for live trades
2. **Trade Details Modal**: Click trade for full details
3. **Charts**: Visual P&L curves
4. **Trade Notes**: Add personal notes to trades
5. **Performance Analytics**: Win rate by stock, time, etc.
6. **Comparison**: Compare backtest vs paper vs live
7. **Alerts**: Notifications for trade executions

---

## 📂 Navigation Structure

```
KeepGaining Dashboard
├── Morning Momentum Alpha (Strategy Overview)
├── Trade Log (← YOU ARE HERE - All Trades)
├── Deployments (Live Strategy Status)
├── Advanced Analytics (Performance Deep Dive)
└── Strategy (Mode Control & Metrics)
```

---

## 💡 Quick Tips

1. **Filter First**: Use filters to narrow down before exporting
2. **Monthly View**: Select month to see specific period
3. **Search Stocks**: Type stock name to find specific trades
4. **Export Often**: Download CSV for offline analysis
5. **Check Stats**: Top cards show filtered statistics

---

*Your complete trade history is now accessible at `/trades`!*
*All 473 validated backtest trades from Oct-Dec 2025*
