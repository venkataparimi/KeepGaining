import asyncio
import sys
import os
import json

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.mcp.technical_analyzer import TechnicalAnalyzer

async def main():
    print("--- 🧪 Testing Technical Analyzer ---")
    analyzer = TechnicalAnalyzer()
    
    symbol = "RELIANCE"
    print(f"Analyzing {symbol}...")
    
    result = await analyzer.get_technical_analysis(symbol)
    
    print(json.dumps(result, indent=2))
    
    if result.get('score') > 0:
        print("\n✅ Technical Analyzer Working!")
    else:
        print("\n❌ Technical Analyzer Returned Empty/Error")

if __name__ == "__main__":
    asyncio.run(main())
