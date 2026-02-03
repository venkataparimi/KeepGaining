"""
Deep Alternative Analysis - Thinking Differently
Looking beyond traditional indicators to find the real edge

Key Questions:
1. WHY did these trades work? (not just WHAT conditions)
2. What do LOSING trades have that WINNERS don't?
3. Is the edge in TIMING (calendar), STOCK SELECTION, or MARKET CONTEXT?
"""
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from pathlib import Path
import json
from collections import defaultdict

def analyze_trades_deeply():
    """Deep analysis looking for non-obvious patterns"""
    
    with open('backend/data/user_trades.json', 'r') as f:
        trades = json.load(f)
    
    print("=" * 100)
    print("🧠 THINKING DIFFERENTLY - ALTERNATIVE ANALYSIS")
    print("=" * 100)
    
    # ========================================
    # 1. CALENDAR/TIMING PATTERNS
    # ========================================
    print("\n📅 1. CALENDAR ANALYSIS")
    print("-" * 80)
    
    dates = [datetime.strptime(t['date'], '%Y-%m-%d') for t in trades]
    
    # Day of week distribution
    dow_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
    dow_counts = defaultdict(int)
    for d in dates:
        dow_counts[dow_names[d.weekday()]] += 1
    
    print("   Day of Week Distribution:")
    for day in dow_names:
        count = dow_counts[day]
        print(f"      {day}: {count} trades {'*' * count}")
    
    # Week of month
    print("\n   Week of Month:")
    for d in sorted(set(dates)):
        week = (d.day - 1) // 7 + 1
        count = sum(1 for t in trades if t['date'] == d.strftime('%Y-%m-%d'))
        ce = sum(1 for t in trades if t['date'] == d.strftime('%Y-%m-%d') and t['optionType'] == 'CE')
        pe = sum(1 for t in trades if t['date'] == d.strftime('%Y-%m-%d') and t['optionType'] == 'PE')
        print(f"      {d.strftime('%Y-%m-%d')} (Week {week}, {dow_names[d.weekday()]}): {count} trades (CE:{ce}, PE:{pe})")
    
    # Gap analysis - trading days gap
    unique_dates = sorted(set(dates))
    gaps = []
    for i in range(1, len(unique_dates)):
        gap = (unique_dates[i] - unique_dates[i-1]).days
        if gap > 1:
            gaps.append((unique_dates[i-1], unique_dates[i], gap))
    
    print("\n   Trading Gaps:")
    for start, end, gap in gaps:
        print(f"      No trades between {start.strftime('%Y-%m-%d')} and {end.strftime('%Y-%m-%d')} ({gap} days)")
    
    # ========================================
    # 2. OPTION TYPE SWITCHING PATTERN
    # ========================================
    print("\n\n📊 2. CE/PE SWITCHING PATTERN")
    print("-" * 80)
    
    for d in sorted(set(dates)):
        day_trades = [t for t in trades if t['date'] == d.strftime('%Y-%m-%d')]
        types = [t['optionType'] for t in day_trades]
        stocks = [t['stockName'] for t in day_trades]
        
        if 'CE' in types and 'PE' in types:
            print(f"   ⚡ {d.strftime('%Y-%m-%d')}: MIXED DAY - Both CE and PE traded")
            print(f"      CE: {[s for t, s in zip(day_trades, stocks) if t['optionType'] == 'CE']}")
            print(f"      PE: {[s for t, s in zip(day_trades, stocks) if t['optionType'] == 'PE']}")
    
    # Pattern: What triggers CE vs PE?
    ce_trades = [t for t in trades if t['optionType'] == 'CE']
    pe_trades = [t for t in trades if t['optionType'] == 'PE']
    
    print(f"\n   Total CE: {len(ce_trades)}, Total PE: {len(pe_trades)}")
    print(f"   CE days: {sorted(set(t['date'] for t in ce_trades))}")
    print(f"   PE days: {sorted(set(t['date'] for t in pe_trades))}")
    
    # ========================================
    # 3. STOCK AFFINITY ANALYSIS
    # ========================================
    print("\n\n🏢 3. STOCK AFFINITY ANALYSIS")
    print("-" * 80)
    
    stock_counts = defaultdict(list)
    for t in trades:
        stock_counts[t['stockName']].append(t)
    
    # Repeated stocks
    print("   Repeated Stocks (potential favorites):")
    for stock, stock_trades in sorted(stock_counts.items(), key=lambda x: -len(x[1])):
        if len(stock_trades) > 1:
            dates = [t['date'] for t in stock_trades]
            types = set(t['optionType'] for t in stock_trades)
            premiums = [t['entryPremium'] for t in stock_trades]
            print(f"\n   📌 {stock}: {len(stock_trades)} trades")
            print(f"      Dates: {dates}")
            print(f"      Types: {types}")
            print(f"      Premiums: ₹{min(premiums):.1f} - ₹{max(premiums):.1f}")
    
    # ========================================
    # 4. PREMIUM ANALYSIS
    # ========================================
    print("\n\n💰 4. PREMIUM/LOT SIZE ANALYSIS")  
    print("-" * 80)
    
    ce_premiums = [t['entryPremium'] for t in ce_trades]
    pe_premiums = [t['entryPremium'] for t in pe_trades]
    
    print(f"   CE Premium Range: ₹{min(ce_premiums):.2f} - ₹{max(ce_premiums):.2f}")
    print(f"   CE Premium Median: ₹{np.median(ce_premiums):.2f}")
    print(f"   PE Premium Range: ₹{min(pe_premiums):.2f} - ₹{max(pe_premiums):.2f}")
    print(f"   PE Premium Median: ₹{np.median(pe_premiums):.2f}")
    
    # Premium buckets
    print("\n   Premium Buckets:")
    buckets = [(0, 10), (10, 30), (30, 100), (100, 200), (200, 1000)]
    for low, high in buckets:
        count = sum(1 for t in trades if low <= t['entryPremium'] < high)
        if count > 0:
            print(f"      ₹{low}-{high}: {count} trades")
    
    # ========================================
    # 5. SECTOR GROUPING
    # ========================================
    print("\n\n🏭 5. POTENTIAL SECTOR GROUPING")
    print("-" * 80)
    
    # Manual sector mapping (approximate)
    sectors = {
        'Metals': ['Hind Zinc', 'Vedl'],
        'Auto': ['Hero Motors', 'TVS Motor'],
        'Telecom': ['Idea'],
        'Fintech': ['Paytm', 'Angel One'],
        'Infra': ['GMR', 'Power India'],
        'FMCG': ['Asian Paints'],
        'Banking': ['Can Bank', 'Axis', 'RBL'],
        'Logistics': ['Delhivery'],
        'Electronics': ['Kaynes'],
        'Aviation': ['Indigo'],
        'Oil & Gas': ['Petronet'],
        'NBFC': ['Shriram Fin'],
        'Real Estate': ['Oberoi Realty', 'Supreme'],
        'Healthcare': ['Max Health'],
        'Exchange': ['IEX']
    }
    
    sector_trades = defaultdict(list)
    for t in trades:
        for sector, stocks in sectors.items():
            if t['stockName'] in stocks:
                sector_trades[sector].append(t)
                break
    
    print("   Sector Distribution:")
    for sector, s_trades in sorted(sector_trades.items(), key=lambda x: -len(x[1])):
        ce = sum(1 for t in s_trades if t['optionType'] == 'CE')
        pe = sum(1 for t in s_trades if t['optionType'] == 'PE')
        print(f"      {sector}: {len(s_trades)} trades (CE:{ce}, PE:{pe})")
    
    # ========================================
    # 6. ALTERNATIVE HYPOTHESES
    # ========================================
    print("\n\n" + "=" * 100)
    print("🎯 ALTERNATIVE HYPOTHESES TO EXPLORE")
    print("=" * 100)
    
    hypotheses = [
        {
            'name': 'HYPOTHESIS 1: Sector Momentum',
            'observation': 'Metals (HindZinc, Vedl) traded 7 times, always CE',
            'strategy': 'When metals sector is strong (HINDZINC up), buy CE on multiple metal stocks',
            'test': 'Check if metal stocks move together; trade sector, not individual'
        },
        {
            'name': 'HYPOTHESIS 2: Calendar Effect',
            'observation': 'Dec 1-2 all CE, Dec 3-5 mostly PE, then mixed',
            'strategy': 'First 2 days of month = bullish, then wait for signals',
            'test': 'Check market behavior first 2 days vs rest of month'
        },
        {
            'name': 'HYPOTHESIS 3: Stock-Specific Timing',
            'observation': 'HINDZINC traded 5 times on 5 different days',
            'strategy': 'Some stocks have recurring patterns; trade same stock repeatedly',
            'test': 'Backtest HINDZINC-only with 14:00 CE entry'
        },
        {
            'name': 'HYPOTHESIS 4: Premium-Based Selection',
            'observation': 'Premiums cluster in ₹5-30 or ₹100-200 ranges',
            'strategy': 'Pick options in specific premium range for risk management',
            'test': 'Check if premium level correlates with win rate'
        },
        {
            'name': 'HYPOTHESIS 5: Market Direction Filter',
            'observation': 'PE trades appear when market may be weak',
            'strategy': 'Check NIFTY direction first, then pick CE or PE accordingly',
            'test': 'Correlate CE/PE days with NIFTY performance'
        }
    ]
    
    for h in hypotheses:
        print(f"\n📌 {h['name']}")
        print(f"   Observation: {h['observation']}")
        print(f"   Potential Strategy: {h['strategy']}")
        print(f"   How to Test: {h['test']}")
    
    print("\n" + "=" * 100)
    print("💡 RECOMMENDED NEXT STEP")
    print("=" * 100)
    print("""
    Based on analysis, the most promising hypothesis is:
    
    🎯 HYPOTHESIS 3: HINDZINC SPECIFIC STRATEGY
    
    Reasoning:
    - You traded HINDZINC 5 out of 28 trades (18%)
    - Always CE (bullish bias on this stock)
    - Strike increases with price: 500 → 510 → 530 → 560 → 580
    - Consistent approach suggests a working pattern
    
    Suggested Test:
    - Backtest HINDZINC-only, CE at 14:00, any day
    - Check if this single stock captures most of your edge
    """)
    
    print("\n✅ Analysis Complete!")


if __name__ == "__main__":
    analyze_trades_deeply()
