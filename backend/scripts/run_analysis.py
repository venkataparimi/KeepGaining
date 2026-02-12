import asyncio
import sys
import os
import json

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.mcp.analysis_engine import MarketAnalysisEngine

async def main():
    print("--- 🚀 Starting Market Analysis Engine ---")
    
    engine = MarketAnalysisEngine(headless=True) # Run headless for speed
    report = await engine.run_analysis()
    
    print("\n--- 📊 Analysis Report ---")
    print(f"Timestamp: {report['timestamp']}")
    
    if report['errors']:
        print("\n❌ Errors Encountered:")
        for err in report['errors']:
            print(f"  - {err}")
            
    print(f"\n📈 Gap Up Stocks (>0.5%): {len(report['gap_up_stocks'])}")
    print(f"🐂 Trendlyne Bullish Stocks: {len(report['trendlyne_bullish'])}")
    
    print("\n🔥 POTENTIAL TRADING SETUPS (Transitioning to Opportunity):")
    if not report['potential_setups']:
        print("  No high-conviction setups found based on current overlap.")
    else:
        for setup in report['potential_setups']:
            print(f"  > {setup['symbol']} | Score: {setup.get('technical_score', 0)}/10 ({setup.get('rating', 'N/A')})")
            print(f"    Gap Up: {setup['gap_up_pct']}% | Price: {setup['price']}")
            
            indicators = setup.get('indicators', {})
            if indicators:
                 print(f"    Tech: RSI {indicators.get('rsi')} ({indicators.get('rsi_status')}) | Trend: {indicators.get('trend')} | MACD: {indicators.get('macd_status')}")
            
            print(f"    Trendlyne: {setup['trendlyne_status']}")
            print(f"    OI validation: {setup.get('oi_support')}")
            print("    ---")
            
    # Dump full report
    with open("market_analysis_latest.json", "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nSaved full detail to backend/market_analysis_latest.json")

if __name__ == "__main__":
    asyncio.run(main())
