"""
Analyze the IEX 140 CE trade to identify the strategy
"""
import ollama

def analyze_trade():
    trade_details = """
    Trade Details:
    - Date: 01-Dec-25
    - Stock: IEX
    - Option: 140 CE (Call Option)
    - Lot Size: 3750 shares
    - Entry Price: ₹9.00
    
    Additional Context Needed:
    - Exit price (if closed)
    - Exit date/time
    - IEX spot price at entry
    - IEX spot price at exit
    - Strike price: 140
    - Any indicators used (RSI, MACD, etc.)
    - Market conditions at entry
    """
    
    prompt = f"""
    You are an expert options trader. Analyze this trade and identify the strategy:
    
    {trade_details}
    
    Based on the available information, provide:
    
    1. **Likely Strategy Type**: What strategy is this? (e.g., Long Call, Breakout Play, Momentum Trade)
    
    2. **Entry Logic**: Why might the trader have entered at ₹9?
       - Was IEX likely breaking out?
       - Was this a support/resistance play?
       - Momentum-based entry?
    
    3. **Risk Analysis**:
       - Maximum loss: ₹9 × 3750 = ₹33,750
       - Break-even: 140 + 9 = ₹149
       - What IEX price was needed for profit?
    
    4. **Possible Exit Scenarios**:
       - Target profit levels
       - Stop loss levels
       - Time decay considerations
    
    5. **Similar Patterns**: What should I look for to replicate this?
    
    Be specific and actionable. Focus on what can be learned from this trade.
    """
    
    print("🤖 Analyzing trade with Ollama...")
    print("=" * 70)
    
    try:
        response = ollama.chat(
            model='llama3',
            messages=[{
                'role': 'user',
                'content': prompt
            }]
        )
        
        analysis = response['message']['content']
        print(analysis)
        
        return analysis
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nMake sure Ollama is running: ollama serve")
        return None

if __name__ == "__main__":
    print("=" * 70)
    print("IEX 140 CE TRADE ANALYSIS")
    print("=" * 70)
    print()
    
    analysis = analyze_trade()
    
    print("\n" + "=" * 70)
    print("ADDITIONAL QUESTIONS TO REFINE ANALYSIS")
    print("=" * 70)
    print()
    print("To provide a more accurate strategy identification, please share:")
    print("1. Exit price and date (if trade was closed)")
    print("2. IEX spot price when you entered (Dec 1)")
    print("3. Why did you choose 140 strike?")
    print("4. What indicators or signals triggered this entry?")
    print("5. Was this part of a larger position or standalone?")
    print()
    print("With this information, I can:")
    print("- Identify the exact strategy")
    print("- Create entry/exit rules")
    print("- Build a backtestable system")
    print("- Find similar opportunities")
