"""
Quick Start: Using Ollama for Trading Analysis
Run this after installing Ollama and pulling a model
"""
import ollama

def test_ollama():
    """Test if Ollama is working"""
    try:
        response = ollama.chat(
            model='llama3',
            messages=[{
                'role': 'user',
                'content': 'Say "Ollama is working!" in one sentence.'
            }]
        )
        print("✅ Ollama is working!")
        print(f"Response: {response['message']['content']}\n")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nMake sure:")
        print("1. Ollama is installed: winget install Ollama.Ollama")
        print("2. Ollama server is running: ollama serve")
        print("3. Model is pulled: ollama pull llama3")
        return False

def analyze_trade(trade_description):
    """Analyze a trade using Ollama"""
    prompt = f"""
    You are a quantitative trading expert. Analyze this trade:
    
    {trade_description}
    
    Provide:
    1. What was the entry logic?
    2. What was the exit logic?
    3. What indicators might have been used?
    4. Risk/Reward assessment
    5. Similar patterns to look for
    
    Be specific and concise.
    """
    
    print("🤖 Analyzing trade with Ollama...")
    
    response = ollama.chat(
        model='llama3',
        messages=[{'role': 'user', 'content': prompt}]
    )
    
    return response['message']['content']

def explain_indicator(indicator_name, current_value):
    """Get explanation of an indicator"""
    prompt = f"""
    Explain the {indicator_name} indicator.
    Current value: {current_value}
    
    What does this value mean?
    Should I buy, sell, or wait?
    Keep it brief and actionable.
    """
    
    response = ollama.chat(
        model='llama3',
        messages=[{'role': 'user', 'content': prompt}]
    )
    
    return response['message']['content']

def generate_strategy_from_trades(winning_trades_list):
    """Generate a trading strategy from winning trades"""
    trades_text = "\n".join([f"- {trade}" for trade in winning_trades_list])
    
    prompt = f"""
    Based on these winning trades, create a systematic trading strategy:
    
    {trades_text}
    
    Provide:
    1. Entry rules (specific conditions with indicators)
    2. Exit rules (profit target and stop loss)
    3. Position sizing recommendation
    4. Risk management rules
    
    Format as a clear, actionable strategy.
    """
    
    response = ollama.chat(
        model='llama3',
        messages=[{'role': 'user', 'content': prompt}]
    )
    
    return response['message']['content']

def interactive_chat():
    """Start an interactive chat session"""
    print("\n" + "="*70)
    print("OLLAMA TRADING ASSISTANT")
    print("="*70)
    print("Ask me anything about trading, strategies, or indicators!")
    print("Type 'exit' to quit\n")
    
    conversation = []
    
    while True:
        user_input = input("You: ")
        
        if user_input.lower() in ['exit', 'quit', 'bye']:
            print("Goodbye!")
            break
        
        conversation.append({
            'role': 'user',
            'content': user_input
        })
        
        response = ollama.chat(
            model='llama3',
            messages=conversation
        )
        
        ai_response = response['message']['content']
        conversation.append({
            'role': 'assistant',
            'content': ai_response
        })
        
        print(f"\nAI: {ai_response}\n")

if __name__ == "__main__":
    print("="*70)
    print("OLLAMA QUICK START FOR TRADING")
    print("="*70)
    print()
    
    # Test connection
    if not test_ollama():
        exit(1)
    
    # Example 1: Analyze a trade
    print("="*70)
    print("EXAMPLE 1: Trade Analysis")
    print("="*70)
    
    trade = """
    Symbol: NIFTY 24000 CE
    Entry: 150 at 9:30 AM when NIFTY broke above 24050
    Exit: 200 at 11:00 AM when RSI hit 75
    Profit: 33%
    """
    
    analysis = analyze_trade(trade)
    print(analysis)
    print()
    
    # Example 2: Explain indicator
    print("="*70)
    print("EXAMPLE 2: Indicator Explanation")
    print("="*70)
    
    explanation = explain_indicator("RSI", "72")
    print(explanation)
    print()
    
    # Example 3: Generate strategy
    print("="*70)
    print("EXAMPLE 3: Strategy Generation")
    print("="*70)
    
    winning_trades = [
        "RELIANCE: Bought at 2450 when RSI crossed 30, sold at 2500 when RSI hit 70",
        "TCS: Bought at 3200 when MACD crossed signal line, sold at 3280 at resistance",
        "INFY: Bought at 1450 on breakout above 1440, sold at 1490 when volume dried up"
    ]
    
    strategy = generate_strategy_from_trades(winning_trades)
    print(strategy)
    print()
    
    # Example 4: Interactive chat (optional)
    print("="*70)
    print("Want to chat interactively? (y/n)")
    if input().lower() == 'y':
        interactive_chat()
    else:
        print("\n✅ Quick start complete!")
        print("\nNext steps:")
        print("1. Check backend/docs/OLLAMA_GUIDE.md for more examples")
        print("2. Integrate with your trading system")
        print("3. Experiment with different models (ollama pull mistral)")
