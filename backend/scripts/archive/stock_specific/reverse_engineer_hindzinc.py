"""
Reverse Engineer Strategy from HINDZINC Trade
Analyze Dec 1, 2025 to identify what triggered the 500 CE entry at 14:00
"""
import asyncio
import asyncpg
import pandas as pd
from datetime import datetime, date, time as dt_time
import numpy as np

async def reverse_engineer_strategy():
    """Analyze HINDZINC on Dec 1 to find the strategy pattern"""
    
    conn = await asyncpg.connect('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    trade_date = date(2025, 12, 1)
    
    print("=" * 80)
    print("🔍 REVERSE ENGINEERING STRATEGY FROM HINDZINC TRADE")
    print("=" * 80)
    print(f"Date: {trade_date}")
    print(f"Entry: 14:00 | Strike: 500 CE | Premium: ₹14.0")
    print()
    
    # Step 1: Check if we have HINDZINC data
    print("📊 Step 1: Checking available data...")
    
    # Check instrument master
    instruments = await conn.fetch("""
        SELECT instrument_id, trading_symbol, instrument_type, lot_size
        FROM instrument_master
        WHERE underlying = 'HINDZINC'
        AND instrument_type IN ('CE', 'PE', 'FUTURES')
        ORDER BY trading_symbol
        LIMIT 20
    """)
    
    if not instruments:
        print("❌ No HINDZINC instruments found in database")
        print("\n💡 ALTERNATIVE APPROACH:")
        print("Since we don't have the actual data, I'll use the trade details to")
        print("hypothesize what the strategy could be based on common patterns.")
        await conn.close()
        await hypothesize_strategy()
        return
    
    print(f"✅ Found {len(instruments)} HINDZINC instruments")
    for inst in instruments[:5]:
        print(f"   {inst['trading_symbol']} ({inst['instrument_type']})")
    
    print()
    
    # Step 2: Try to find 500 CE option
    print("📈 Step 2: Looking for 500 CE option...")
    
    ce_options = [i for i in instruments if i['instrument_type'] == 'CE' and '500CE' in i['trading_symbol']]
    
    if ce_options:
        print(f"✅ Found {len(ce_options)} matching 500 CE options")
        selected = ce_options[0]
        print(f"   Selected: {selected['trading_symbol']}")
        
        # Try to get data for Dec 1
        # Note: We need to check what tables exist
        print("\n📊 Step 3: Checking for price data...")
        
        # Check available tables
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
        """)
        
        table_names = [t['table_name'] for t in tables]
        print(f"Available tables: {', '.join(table_names[:10])}")
        
    else:
        print("❌ No 500 CE option found")
    
    await conn.close()
    
    # Since we likely don't have the data, hypothesize the strategy
    print("\n" + "=" * 80)
    print("💡 HYPOTHESIZING STRATEGY BASED ON TRADE PARAMETERS")
    print("=" * 80)
    await hypothesize_strategy()

async def hypothesize_strategy():
    """
    Based on the trade parameters, hypothesize what the strategy could be
    """
    
    print("\n📋 TRADE PARAMETERS ANALYSIS:")
    print("-" * 80)
    print("Entry Time:    14:00 (2:00 PM)")
    print("Strike:        500 CE")
    print("Entry Premium: ₹14.0")
    print("Stock:         HINDZINC")
    print()
    
    print("🔍 POSSIBLE STRATEGY PATTERNS:")
    print("=" * 80)
    
    # Pattern 1: Post-Lunch Breakout
    print("\n1️⃣  POST-LUNCH BREAKOUT STRATEGY")
    print("-" * 80)
    print("Hypothesis: Stock breaks out after lunch consolidation")
    print()
    print("Possible Entry Criteria:")
    print("  • Time: 14:00 (post-lunch session starts)")
    print("  • Trigger: Price breaks above morning high")
    print("  • Confirmation: Volume surge at breakout")
    print("  • Strike: ATM or slightly OTM CE")
    print()
    print("If 500 CE premium is ₹14, spot could be:")
    print("  • Scenario A: Spot ~₹495-505 (ATM)")
    print("  • Scenario B: Spot ~₹480-490 (OTM)")
    print()
    print("Entry Rules:")
    print("  ✓ Wait until 14:00")
    print("  ✓ Check if price > morning high")
    print("  ✓ Check if volume > average")
    print("  ✓ Buy ATM CE option")
    print()
    print("Exit Rules:")
    print("  ✓ Target: 50-100% on premium")
    print("  ✓ Stop: -30 to -40%")
    print("  ✓ Time: Exit by 15:30 or EOD")
    print()
    
    # Pattern 2: Afternoon Momentum
    print("\n2️⃣  AFTERNOON MOMENTUM STRATEGY")
    print("-" * 80)
    print("Hypothesis: Capture afternoon momentum after morning consolidation")
    print()
    print("Possible Entry Criteria:")
    print("  • Time: 14:00 (fixed time entry)")
    print("  • Condition: Stock shows positive momentum in morning")
    print("  • Filter: Morning move > 1-2%")
    print("  • Strike: ATM CE for maximum leverage")
    print()
    print("Entry Rules:")
    print("  ✓ Calculate morning move (9:15 to 14:00)")
    print("  ✓ If move > +1%, enter CE at 14:00")
    print("  ✓ Select ATM strike")
    print("  ✓ Enter with fixed lot size")
    print()
    print("Exit Rules:")
    print("  ✓ Target: +50% on premium")
    print("  ✓ Stop: -40% on premium")
    print("  ✓ Time: Exit at 15:30 or EOD")
    print()
    
    # Pattern 3: Mean Reversion
    print("\n3️⃣  AFTERNOON REVERSAL STRATEGY")
    print("-" * 80)
    print("Hypothesis: Stock reverses from morning dip")
    print()
    print("Possible Entry Criteria:")
    print("  • Time: 14:00")
    print("  • Condition: Stock dipped in morning, shows reversal")
    print("  • Trigger: Price crosses above VWAP or key level")
    print("  • Strike: ATM CE for reversal play")
    print()
    print("Entry Rules:")
    print("  ✓ Morning move < -1% (dip)")
    print("  ✓ At 14:00, check if price > VWAP")
    print("  ✓ Enter CE if reversal confirmed")
    print()
    
    # Pattern 4: Time-Based Statistical Edge
    print("\n4️⃣  TIME-BASED STATISTICAL EDGE")
    print("-" * 80)
    print("Hypothesis: Statistical edge at 14:00 entry")
    print()
    print("Possible Entry Criteria:")
    print("  • Time: Always 14:00 (no other condition)")
    print("  • Logic: Historical data shows edge at this time")
    print("  • Strike: Fixed strike or ATM")
    print("  • Direction: Always CE (bullish bias)")
    print()
    
    print("\n" + "=" * 80)
    print("🎯 RECOMMENDED APPROACH TO IDENTIFY THE STRATEGY")
    print("=" * 80)
    print()
    print("To determine which pattern this is, I need to analyze:")
    print()
    print("1. HINDZINC price movement on Dec 1, 2025:")
    print("   • What was the open price (9:15 AM)?")
    print("   • What was the price at 14:00?")
    print("   • What was the morning high/low?")
    print("   • What was the volume pattern?")
    print()
    print("2. Option behavior:")
    print("   • Was 500 CE ATM, OTM, or ITM at 14:00?")
    print("   • What was the IV (Implied Volatility)?")
    print("   • What happened to premium after entry?")
    print()
    print("3. Market context:")
    print("   • Was there any news/event?")
    print("   • How did NIFTY/Market perform?")
    print("   • Was there sector momentum?")
    print()
    
    print("=" * 80)
    print("💡 NEXT STEPS")
    print("=" * 80)
    print()
    print("Option A: If you have more trade examples")
    print("  → Provide 5-10 more trades")
    print("  → I'll find common patterns across all trades")
    print("  → Define the strategy rules")
    print()
    print("Option B: If you know the exit details")
    print("  → Tell me exit time, premium, P&L")
    print("  → I can infer the exit rules")
    print("  → Build strategy based on that")
    print()
    print("Option C: If you remember the market context")
    print("  → What was HINDZINC doing that day?")
    print("  → Why did you enter at 14:00?")
    print("  → What made you choose 500 CE?")
    print()
    print("Option D: Use AI to analyze similar patterns")
    print("  → I can scan historical data for similar setups")
    print("  → Find days where 14:00 entry would work")
    print("  → Backtest the pattern")
    print()
    
    print("=" * 80)
    print("🚀 WHAT I'LL DO NOW")
    print("=" * 80)
    print()
    print("I'll create a script that:")
    print("1. Scans for 14:00 entry opportunities")
    print("2. Tests multiple hypothesis (breakout, momentum, reversal)")
    print("3. Backtests each pattern")
    print("4. Shows you which pattern has best results")
    print()
    print("This way, we can discover the strategy from data!")
    print()

if __name__ == "__main__":
    asyncio.run(reverse_engineer_strategy())
