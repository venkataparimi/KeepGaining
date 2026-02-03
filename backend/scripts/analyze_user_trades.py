"""
Analyze 28 User Trades - Full Pattern Discovery
"""
import asyncio
import json
from datetime import datetime, date
from collections import defaultdict
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from trade_analyzer import TradeAnalyzer
from enhanced_rag_context import EnhancedRAGContextBuilder
from ollama_strategy_analyzer import OllamaStrategyAnalyzer

# Stock name mapping
STOCK_MAPPING = {
    'IEX': 'IEX',
    'HIND ZINC': 'HINDZINC',
    'HERO MOTORS': 'HEROMOTOCO',
    'TVS MOTOR': 'TVSMOTOR',
    'IDEA': 'IDEA',
    'PAYTM': 'PAYTM',
    'GMR': 'GMRAIRPORT',
    'ASIAN PAINTS': 'ASIANPAINT',
    'CAN BANK': 'CANBK',
    'DELHIVERY': 'DELHIVERY',
    'ANGEL ONE': 'ANGELONE',
    'KAYNES': 'KAYNES',
    'INDIGO': 'INDIGO',
    'PETRONET': 'PETRONET',
    'POWER INDIA': 'POWERINDIA',
    'SHRIRAM FIN': 'SHRIRAMFIN',
    'OBEROI REALTY': 'OBEROIRLTY',
    'VEDL': 'VEDL',
    'SUPREME': 'SUPREMEIND',
    'AXIS': 'AXISBANK',
    'RBL': 'RBLBANK',
    'MAX HEALTH': 'MAXHEALTH',
}


def normalize_stock(name):
    """Normalize stock name to database format"""
    upper = name.upper().strip()
    return STOCK_MAPPING.get(upper, upper.replace(' ', ''))


async def analyze_all_trades():
    """Analyze all 28 trades"""
    
    # Load trades
    with open('backend/data/user_trades.json', 'r') as f:
        trades = json.load(f)
    
    print("=" * 80)
    print("🔍 ANALYZING 28 USER TRADES")
    print("=" * 80)
    
    # Quick statistics
    print(f"\n📊 QUICK OVERVIEW:")
    print(f"   Total Trades: {len(trades)}")
    
    # Group by date
    by_date = defaultdict(list)
    for t in trades:
        by_date[t['date']].append(t)
    
    print(f"   Trading Days: {len(by_date)}")
    print(f"   Dates: {', '.join(sorted(by_date.keys()))}")
    
    # Group by option type
    ce_trades = [t for t in trades if t['optionType'] == 'CE']
    pe_trades = [t for t in trades if t['optionType'] == 'PE']
    
    print(f"\n   CE Trades: {len(ce_trades)} (Bullish)")
    print(f"   PE Trades: {len(pe_trades)} (Bearish)")
    
    # Repeated stocks
    stock_counts = defaultdict(int)
    for t in trades:
        stock_counts[normalize_stock(t['stockName'])] += 1
    
    repeated = {k: v for k, v in stock_counts.items() if v > 1}
    if repeated:
        print(f"\n   Repeated Stocks:")
        for stock, count in sorted(repeated.items(), key=lambda x: -x[1]):
            print(f"      {stock}: {count} trades")
    
    print("\n" + "-" * 80)
    
    # Analyze each trade
    analyzer = TradeAnalyzer('postgresql://user:password@127.0.0.1:5432/keepgaining')
    await analyzer.connect()
    
    analyzed = []
    failed = []
    
    print("\n📈 ANALYZING EACH TRADE:\n")
    
    for i, trade in enumerate(trades, 1):
        stock = normalize_stock(trade['stockName'])
        
        # Prepare trade for analyzer
        trade_data = {
            'date': trade['date'],
            'stock': stock,
            'strike': trade['strike'],
            'optionType': trade['optionType'],
            'entryPremium': trade['entryPremium'],
            'entryTime': '14:00'  # Assumed
        }
        
        try:
            analysis = await analyzer.analyze_trade(trade_data)
            
            if analysis.spot_price:
                analyzed.append(analysis.to_dict())
                status = "✅"
                details = f"RSI={analysis.rsi_14:.1f}, Range={analysis.range_position:.1f}%" if analysis.rsi_14 else "Partial data"
            else:
                failed.append(trade_data)
                status = "⚠️"
                details = "No market data"
            
            print(f"   {i:2d}. {status} {trade['date']} {stock} {trade['strike']} {trade['optionType']} - {details}")
            
        except Exception as e:
            failed.append(trade_data)
            print(f"   {i:2d}. ❌ {trade['date']} {stock} - Error: {str(e)[:50]}")
    
    await analyzer.close()
    
    print(f"\n   Analyzed: {len(analyzed)}, Failed: {len(failed)}")
    
    # Pattern Analysis
    if analyzed:
        print("\n" + "=" * 80)
        print("🎯 PATTERN ANALYSIS")
        print("=" * 80)
        
        # Group by option type
        ce_analyzed = [a for a in analyzed if a['option_type'] == 'CE']
        pe_analyzed = [a for a in analyzed if a['option_type'] == 'PE']
        
        print(f"\n📊 CE Trades ({len(ce_analyzed)}):")
        if ce_analyzed:
            avg_rsi = sum(a['rsi_14'] for a in ce_analyzed if a.get('rsi_14')) / len([a for a in ce_analyzed if a.get('rsi_14')]) if any(a.get('rsi_14') for a in ce_analyzed) else 0
            avg_range = sum(a['range_position'] for a in ce_analyzed if a.get('range_position')) / len([a for a in ce_analyzed if a.get('range_position')]) if any(a.get('range_position') for a in ce_analyzed) else 0
            print(f"   Avg RSI: {avg_rsi:.1f}")
            print(f"   Avg Range Position: {avg_range:.1f}%")
        
        print(f"\n📊 PE Trades ({len(pe_analyzed)}):")
        if pe_analyzed:
            avg_rsi = sum(a['rsi_14'] for a in pe_analyzed if a.get('rsi_14')) / len([a for a in pe_analyzed if a.get('rsi_14')]) if any(a.get('rsi_14') for a in pe_analyzed) else 0
            avg_range = sum(a['range_position'] for a in pe_analyzed if a.get('range_position')) / len([a for a in pe_analyzed if a.get('range_position')]) if any(a.get('range_position') for a in pe_analyzed) else 0
            print(f"   Avg RSI: {avg_rsi:.1f}")
            print(f"   Avg Range Position: {avg_range:.1f}%")
        
        # Use LLM for pattern discovery
        print("\n" + "=" * 80)
        print("🤖 AI PATTERN DISCOVERY")
        print("=" * 80)
        
        llm = OllamaStrategyAnalyzer(model="llama3")
        connected = await llm.check_connection()
        
        if connected:
            print("\n📊 Sending trades to LLM for analysis...")
            patterns = await llm.discover_patterns(analyzed)
            
            print("\n🎯 DISCOVERED PATTERNS:")
            print("-" * 80)
            print(patterns)
            print("-" * 80)
            
            # Get formal rules
            print("\n📋 Generating strategy rules...")
            rules = await llm.suggest_strategy_rules(patterns, analyzed)
            
            print("\n📋 STRATEGY RULES:")
            print("-" * 80)
            print(rules)
            print("-" * 80)
            
            # Save results
            results = {
                'total_trades': len(trades),
                'analyzed': len(analyzed),
                'ce_trades': len(ce_analyzed),
                'pe_trades': len(pe_analyzed),
                'patterns': patterns,
                'rules': rules,
                'analyzed_trades': analyzed
            }
            
            with open('backend/data/trade_analysis_results.json', 'w') as f:
                json.dump(results, f, indent=2, default=str)
            
            print(f"\n📄 Results saved to: backend/data/trade_analysis_results.json")
        else:
            print("⚠️ Ollama not available for AI analysis")
    
    print("\n✅ Analysis Complete!")


if __name__ == "__main__":
    asyncio.run(analyze_all_trades())
