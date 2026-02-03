"""
Test script for Comet with Perplexity Pro API
Run: python test_comet_perplexity.py
"""
import asyncio
import os
from dotenv import load_dotenv
from app.comet.mcp_client_perplexity import CometMCP, MCPClient

# Load environment variables
load_dotenv()


async def test_async_client():
    """Test async CometMCP client"""
    print("\n" + "="*60)
    print("Testing Async CometMCP Client")
    print("="*60 + "\n")
    
    try:
        comet = CometMCP()
        
        # Test 1: Simple market query
        print("Test 1: Simple Market Query")
        print("-" * 60)
        result = await comet.query(
            "What's the current sentiment on Indian banking stocks today?"
        )
        print(f"Sentiment: {result.get('sentiment')}")
        print(f"Confidence: {result.get('confidence')}")
        print(f"Key Insights: {result.get('key_insights', [])[:2]}")
        print(f"Citations: {len(result.get('citations', []))} sources")
        print(f"Model: {result.get('model')}")
        print(f"Tokens used: {result.get('usage', {}).get('total_tokens')}")
        
        # Test 2: Specific stock analysis
        print("\n\nTest 2: Specific Stock Analysis")
        print("-" * 60)
        result = await comet.analyze({
            "query": "Analyze RELIANCE stock. Any recent news or developments?",
            "symbols": ["RELIANCE"],
            "focus": "trading_opportunities",
            "timeframe": "today"
        })
        print(f"Sentiment: {result.get('sentiment')}")
        print(f"Trading Signals: {len(result.get('trading_signals', []))}")
        if result.get('trading_signals'):
            for signal in result.get('trading_signals', [])[:2]:
                print(f"  - {signal.get('symbol')}: {signal.get('action')} ({signal.get('reasoning', '')[:80]}...)")
        print(f"Risks: {len(result.get('risks', []))}")
        
        # Test 3: Reasoning model for complex analysis
        print("\n\nTest 3: Complex Analysis (Reasoning Model)")
        print("-" * 60)
        result = await comet.analyze(
            {
                "query": "The US Fed just raised rates. How will this impact Indian IT stocks in the next week?",
                "focus": "macro_impact",
                "timeframe": "short_term"
            },
            model="reasoning"
        )
        print(f"Confidence: {result.get('confidence')}")
        print(f"Key Insights:")
        for insight in result.get('key_insights', [])[:3]:
            print(f"  - {insight}")
        print(f"Data Freshness: {result.get('data_freshness')}")
        
        # Test 4: Conversation context
        print("\n\nTest 4: Conversation Context")
        print("-" * 60)
        conv_id = "test_session_1"
        
        result1 = await comet.analyze(
            {"query": "What's happening with NIFTY today?"},
            conversation_id=conv_id
        )
        print(f"First query sentiment: {result1.get('sentiment')}")
        
        result2 = await comet.analyze(
            {"query": "Should I buy or wait?"},
            conversation_id=conv_id
        )
        print(f"Follow-up query result: {result2.get('key_insights', [''])[0][:100]}...")
        print(f"Conversation history length: {len(comet.get_conversation_history(conv_id))} messages")
        
        print("\n✅ All async tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_sync_client():
    """Test synchronous MCPClient wrapper"""
    print("\n" + "="*60)
    print("Testing Synchronous MCPClient")
    print("="*60 + "\n")
    
    try:
        comet = MCPClient()
        
        # Test synchronous query (for notebooks)
        print("Test: Synchronous Query")
        print("-" * 60)
        result = comet.query(
            "Quick sentiment check on NIFTY Bank index"
        )
        print(f"Sentiment: {result.get('sentiment')}")
        print(f"Confidence: {result.get('confidence')}")
        print(f"Key Insights: {result.get('key_insights', [])[:1]}")
        
        print("\n✅ Sync test passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_with_templates():
    """Test prompt template integration"""
    print("\n" + "="*60)
    print("Testing Prompt Template Integration")
    print("="*60 + "\n")
    
    try:
        comet = CometMCP()
        
        # Test signal analysis template
        print("Test: Signal Analysis Template")
        print("-" * 60)
        result = await comet.analyze_with_template(
            "signal_analysis",
            {
                "symbol": "NIFTY",
                "signal_type": "BULLISH_BREAKOUT",
                "entry_price": 22000,
                "current_price": 22150,
                "timeframe": "15m",
                "indicators": "RSI: 68, MACD: Bullish crossover, Volume: Above average",
                "market_context": "Strong uptrend on higher timeframes, banking stocks showing strength"
            }
        )
        print(f"Sentiment: {result.get('sentiment')}")
        print(f"Confidence: {result.get('confidence')}")
        if result.get('trading_signals'):
            signal = result.get('trading_signals')[0]
            print(f"Signal: {signal.get('action')} - {signal.get('reasoning', '')[:100]}...")
        
        print("\n✅ Template test passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_pro_features():
    """Test Perplexity Pro specific features"""
    print("\n" + "="*60)
    print("Testing Perplexity Pro Features")
    print("="*60 + "\n")
    
    try:
        comet = CometMCP()
        
        # Test 1: Real-time web search
        print("Test 1: Real-time Market News")
        print("-" * 60)
        result = await comet.query(
            "What are the top 3 news stories affecting Indian stock market RIGHT NOW?"
        )
        print(f"Data Freshness: {result.get('data_freshness')}")
        print(f"Citations: {len(result.get('citations', []))} sources")
        print(f"Key Insights:")
        for insight in result.get('key_insights', [])[:3]:
            print(f"  - {insight[:120]}...")
        
        # Test 2: Multi-source verification
        print("\n\nTest 2: Multi-Source Analysis")
        print("-" * 60)
        result = await comet.analyze({
            "query": "Is there insider buying/selling activity in TATA Motors recently?",
            "focus": "fundamental_analysis"
        })
        print(f"Confidence: {result.get('confidence')}")
        print(f"Citations: {result.get('citations', [])[:3]}")
        
        # Test 3: Sector comparison
        print("\n\nTest 3: Sector Comparison")
        print("-" * 60)
        result = await comet.query(
            "Compare the performance and outlook of IT vs Banking sector in India for next month"
        )
        print(f"Sentiment: {result.get('sentiment')}")
        if result.get('trading_signals'):
            print(f"Signals:")
            for signal in result.get('trading_signals', []):
                print(f"  - {signal.get('symbol', 'SECTOR')}: {signal.get('action')} ({signal.get('timeframe')})")
        
        print("\n✅ Pro features test passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests"""
    print("\n🚀 Comet Perplexity Pro Test Suite")
    print("=" * 60)
    
    # Check for API key
    if not os.getenv("PERPLEXITY_API_KEY"):
        print("\n❌ PERPLEXITY_API_KEY not found in environment!")
        print("Add it to your .env file:")
        print('PERPLEXITY_API_KEY="pplx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"')
        return
    
    results = []
    
    # Run async tests
    results.append(await test_async_client())
    
    # Run sync tests
    results.append(test_sync_client())
    
    # Run template tests
    results.append(await test_with_templates())
    
    # Run Pro features tests
    results.append(await test_pro_features())
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("\n✅ All tests passed! Comet is ready to use.")
        print("\nNext steps:")
        print("1. Review the output and verify API is working correctly")
        print("2. Check token usage and costs")
        print("3. Integrate into your trading strategies")
        print("4. Try the examples in PERPLEXITY_PRO_IMPLEMENTATION.md")
    else:
        print(f"\n⚠️ {total - passed} test(s) failed. Check errors above.")


if __name__ == "__main__":
    asyncio.run(main())
