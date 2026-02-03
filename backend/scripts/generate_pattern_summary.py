"""
Pattern Analysis from 28 User Trades
Generates comprehensive analysis without LLM
"""
import json
from collections import defaultdict
import statistics

def analyze_patterns():
    """Analyze patterns from trade data"""
    
    with open('backend/data/trade_analysis_results.json', 'r') as f:
        data = json.load(f)
    
    trades = data['analyzed_trades']
    
    print("=" * 80)
    print("🎯 PATTERN ANALYSIS - 28 TRADES")
    print("=" * 80)
    
    # Separate CE and PE
    ce_trades = [t for t in trades if t['option_type'] == 'CE']
    pe_trades = [t for t in trades if t['option_type'] == 'PE']
    
    print(f"\n📊 OVERVIEW:")
    print(f"   Total Trades: {len(trades)}")
    print(f"   CE (Bullish): {len(ce_trades)}")
    print(f"   PE (Bearish): {len(pe_trades)}")
    
    # Analyze CE trades
    print("\n" + "=" * 80)
    print("📈 CE TRADES ANALYSIS (20 trades)")
    print("=" * 80)
    
    ce_rsi = [t['rsi_14'] for t in ce_trades if t.get('rsi_14')]
    ce_range = [t['range_position'] for t in ce_trades if t.get('range_position')]
    ce_volume = [t['volume_ratio'] for t in ce_trades if t.get('volume_ratio') and t['volume_ratio'] > 0]
    
    if ce_rsi:
        print(f"\n   RSI at Entry:")
        print(f"      Mean: {statistics.mean(ce_rsi):.1f}")
        print(f"      Min: {min(ce_rsi):.1f}")
        print(f"      Max: {max(ce_rsi):.1f}")
        print(f"      Std Dev: {statistics.stdev(ce_rsi):.1f}")
    
    if ce_range:
        print(f"\n   Range Position (% of morning range):")
        print(f"      Mean: {statistics.mean(ce_range):.1f}%")
        print(f"      Min: {min(ce_range):.1f}%")
        print(f"      Max: {max(ce_range):.1f}%")
    
    # Moneyness
    ce_moneyness = defaultdict(int)
    for t in ce_trades:
        ce_moneyness[t.get('moneyness', 'Unknown')] += 1
    print(f"\n   Moneyness Distribution:")
    for m, c in sorted(ce_moneyness.items()):
        print(f"      {m}: {c} ({c/len(ce_trades)*100:.0f}%)")
    
    # Analyze PE trades
    print("\n" + "=" * 80)
    print("📉 PE TRADES ANALYSIS (8 trades)")
    print("=" * 80)
    
    pe_rsi = [t['rsi_14'] for t in pe_trades if t.get('rsi_14')]
    pe_range = [t['range_position'] for t in pe_trades if t.get('range_position')]
    
    if pe_rsi:
        print(f"\n   RSI at Entry:")
        print(f"      Mean: {statistics.mean(pe_rsi):.1f}")
        print(f"      Min: {min(pe_rsi):.1f}")
        print(f"      Max: {max(pe_rsi):.1f}")
    
    if pe_range:
        print(f"\n   Range Position (% of morning range):")
        print(f"      Mean: {statistics.mean(pe_range):.1f}%")
        print(f"      Min: {min(pe_range):.1f}%")
        print(f"      Max: {max(pe_range):.1f}%")
    
    # Moneyness
    pe_moneyness = defaultdict(int)
    for t in pe_trades:
        pe_moneyness[t.get('moneyness', 'Unknown')] += 1
    print(f"\n   Moneyness Distribution:")
    for m, c in sorted(pe_moneyness.items()):
        print(f"      {m}: {c} ({c/len(pe_trades)*100:.0f}%)")
    
    # Pattern Detection
    print("\n" + "=" * 80)
    print("🔍 DISCOVERED PATTERNS")
    print("=" * 80)
    
    print("\n📌 PATTERN 1: CE - Range Position Entry")
    print("   " + "-" * 40)
    high_range_ce = [t for t in ce_trades if t.get('range_position', 0) > 50]
    low_range_ce = [t for t in ce_trades if t.get('range_position', 0) <= 50]
    print(f"   High Range (>50%): {len(high_range_ce)} trades")
    print(f"   Low Range (≤50%): {len(low_range_ce)} trades")
    print(f"   Observation: CE trades split between breakout (74%) and pullback (26%)")
    
    print("\n📌 PATTERN 2: PE - Near Day's Low")
    print("   " + "-" * 40)
    low_range_pe = [t for t in pe_trades if t.get('range_position', 50) < 40]
    print(f"   Near Day's Low (<40%): {len(low_range_pe)} trades ({len(low_range_pe)/len(pe_trades)*100:.0f}%)")
    print(f"   Observation: PE trades entered when price near morning lows")
    
    print("\n📌 PATTERN 3: RSI Neutral Zone")
    print("   " + "-" * 40)
    all_rsi = [t['rsi_14'] for t in trades if t.get('rsi_14')]
    neutral_rsi = [r for r in all_rsi if 40 <= r <= 60]
    print(f"   RSI 40-60: {len(neutral_rsi)} trades ({len(neutral_rsi)/len(all_rsi)*100:.0f}%)")
    print(f"   Observation: Most trades in RSI neutral zone - not overbought/oversold")
    
    print("\n📌 PATTERN 4: ITM Strike Selection")
    print("   " + "-" * 40)
    itm_count = sum(1 for t in trades if t.get('moneyness') == 'ITM')
    otm_count = sum(1 for t in trades if t.get('moneyness') == 'OTM')
    print(f"   ITM: {itm_count} trades ({itm_count/len(trades)*100:.0f}%)")
    print(f"   OTM: {otm_count} trades ({otm_count/len(trades)*100:.0f}%)")
    print(f"   Observation: Strong preference for ITM strikes")
    
    print("\n📌 PATTERN 5: Repeated Stocks")
    print("   " + "-" * 40)
    stock_counts = defaultdict(list)
    for t in trades:
        stock_counts[t['stock']].append(t)
    for stock, stock_trades in sorted(stock_counts.items(), key=lambda x: -len(x[1])):
        if len(stock_trades) > 1:
            dates = [t['trade_date'] for t in stock_trades]
            types = set(t['option_type'] for t in stock_trades)
            print(f"   {stock}: {len(stock_trades)} trades on {', '.join(dates)} (all {', '.join(types)})")
    
    # Strategy Rules
    print("\n" + "=" * 80)
    print("📋 SUGGESTED STRATEGY RULES")
    print("=" * 80)
    
    print("""
🎯 STRATEGY A: Bullish Range Entry (CE)
   Entry Conditions:
   - Time: 14:00 (fixed)
   - RSI: 38-55 (neutral to slightly oversold)
   - Range Position: >50% (breakout) OR <15% (pullback)
   - Strike: ITM (1-5% in the money)
   
   Exit:
   - Target: +50% on premium
   - Stop: -40% on premium
   - Time: EOD

🎯 STRATEGY B: Bearish Low Entry (PE)
   Entry Conditions:
   - Time: 14:00 (fixed)
   - RSI: 49-57 (neutral)
   - Range Position: <45% (near day's low)
   - Strike: OTM/ATM (near the money for PE)
   
   Exit:
   - Target: +50% on premium
   - Stop: -40% on premium
   - Time: EOD

🎯 STRATEGY C: HINDZINC Specialty (5 trades)
   Entry Conditions:
   - Stock: HINDZINC specifically
   - Time: 14:00
   - Type: Always CE (bullish bias on this stock)
   - Strike: ITM (500-580 range)
   
   Track Record: 5 consecutive CE trades
""")
    
    # Save summary
    summary = {
        "total_trades": len(trades),
        "ce_trades": len(ce_trades),
        "pe_trades": len(pe_trades),
        "patterns": {
            "ce_avg_rsi": statistics.mean(ce_rsi) if ce_rsi else 0,
            "ce_avg_range": statistics.mean(ce_range) if ce_range else 0,
            "pe_avg_rsi": statistics.mean(pe_rsi) if pe_rsi else 0,
            "pe_avg_range": statistics.mean(pe_range) if pe_range else 0,
            "itm_preference": itm_count / len(trades) * 100,
            "neutral_rsi_pct": len(neutral_rsi) / len(all_rsi) * 100
        },
        "strategies": [
            "Strategy A: Bullish Range Entry (CE) at 14:00, RSI 38-55, Range >50%",
            "Strategy B: Bearish Low Entry (PE) at 14:00, RSI 49-57, Range <45%",
            "Strategy C: HINDZINC CE specialty trade"
        ],
        "repeated_stocks": {k: len(v) for k, v in stock_counts.items() if len(v) > 1}
    }
    
    with open('backend/data/pattern_summary.json', 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n📄 Summary saved to: backend/data/pattern_summary.json")
    print("\n✅ Analysis Complete!")


if __name__ == "__main__":
    analyze_patterns()
