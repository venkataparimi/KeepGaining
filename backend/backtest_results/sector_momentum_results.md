# Sector Momentum Strategy Backtest Results

## Strategy Overview

The Sector Momentum Strategy identifies strong sectors at market open and trades stocks within those sectors.

### Strategy Logic:
1. At market open (9:15-9:30 AM), rank all sector indices by:
   - Gap up/down from previous close
   - First 15-min candle strength (body %, high-low range)
   - Momentum (price vs 9 EMA)
   
2. Select top N strongest sectors for bullish trades (or weakest for bearish)

3. Within selected sectors, identify stocks with:
   - Strong alignment with sector direction
   - Good volume (above average)
   - Clear breakout/breakdown pattern

4. Entry: Buy CE/PE based on sector direction with tight stop loss
   Exit: 1:2 RR, or time-based exit at EOD

## Configuration Used

```python
SectorConfig(
    top_sectors_count=3,
    max_trades_per_sector=3,
    max_total_trades=8,
    risk_reward_ratio=2.0,
    min_stock_alignment=0.4,  # Relaxed from 0.7 
    min_stock_volume_multiplier=0.8,  # Relaxed from 1.2
)
```

## Backtest Results (30 Days: Oct 23 - Nov 28, 2025)

### Both Directions (CE + PE)

| Metric | Value |
|--------|-------|
| Days Traded | 26 |
| Total Trades | 205 |
| Win Rate | 45.9% |
| **Total P&L** | **+0.30%** |
| Avg P&L/Trade | +0.001% |

**Direction Breakdown:**
- CE Trades: 178, Win Rate: 46.6%, P&L: +5.94%
- PE Trades: 27, Win Rate: 40.7%, P&L: -5.64%

### Bullish Only (CE trades only)

| Metric | Value |
|--------|-------|
| Days Traded | 24 |
| Total Trades | 178 |
| Win Rate | 46.6% |
| **Total P&L** | **+5.94%** |
| Avg P&L/Trade | +0.033% |

## Sector Performance (Bullish Only)

| Sector Index | Trades | Win Rate | P&L |
|--------------|--------|----------|-----|
| NIFTY BANK | 19 | 57.9% | +3.68% |
| NIFTY ENERGY | 29 | 51.7% | +1.72% |
| NIFTY INFRA | 29 | 41.4% | +1.64% |
| NIFTY IT | 19 | 47.4% | +1.52% |
| NIFTY METAL | 19 | 57.9% | +1.20% |
| NIFTY REALTY | 12 | 58.3% | +0.73% |
| NIFTY AUTO | 15 | 40.0% | +0.09% |
| NIFTY FIN SERVICE | 11 | 36.4% | -0.09% |
| NIFTY FMCG | 10 | 30.0% | -2.07% |
| NIFTY PHARMA | 15 | 33.3% | -2.47% |

## Exit Reason Analysis

| Exit Reason | Trades | P&L |
|-------------|--------|-----|
| EOD (End of Day) | 159 | +19.16% |
| SL_HIT | 18 | -15.00% |
| TARGET_HIT (2:1 RR) | 1 | +1.78% |

## Key Insights

### What Works:
1. **Bullish trades outperform bearish trades significantly** (+5.94% vs -5.64%)
2. **Banking sector is most profitable** (57.9% WR, +3.68% P&L)
3. **Metal sector has highest win rate** (57.9% WR, +1.20% P&L)
4. **EOD exits contribute most profits** (+19.16% from 159 trades)

### What Doesn't Work:
1. **Bearish (PE) trades** - negative expectancy
2. **FMCG and Pharma sectors** - consistently underperform
3. **Target hits are rare** - only 1 in 178 trades hit 2:1 target
4. **SL hits are costly** (-15.00% from just 18 trades)

## Recommendations

1. **Focus on bullish trades only** - avoid PE trades
2. **Prioritize best sectors:** NIFTY BANK, NIFTY METAL, NIFTY REALTY
3. **Avoid:** NIFTY PHARMA, NIFTY FMCG
4. **Consider adjusting risk:reward** - 2:1 rarely hit, try 1.5:1
5. **Consider trailing stop** instead of fixed target

## Best/Worst Days

**Best Days:**
- 2025-10-27: +3.69% (8 trades)
- 2025-10-31: +3.53% (8 trades)
- 2025-10-29: +2.90% (8 trades)

**Worst Days:**
- 2025-11-07: -2.53% (8 trades)
- 2025-11-24: -2.76% (8 trades)
- 2025-11-21: -4.56% (8 trades)

## Comparison with Previous Strategies

| Strategy | Win Rate | Total P&L | Avg P&L/Trade |
|----------|----------|-----------|---------------|
| EMA Scalping | 28.6% | -2.59% | -0.09% |
| Momentum + Slippage | 42.0% | -17.21% | -0.43% |
| **Sector Momentum (Bullish)** | **46.6%** | **+5.94%** | **+0.033%** |

The Sector Momentum Strategy shows improvement over previous strategies, particularly when focusing on bullish trades only.

---
*Generated: 2025-12-01*
