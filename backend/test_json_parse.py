import json

# Simulate the response from Perplexity
response = '''{
    "sentiment": 0.58,
    "confidence": 0.78,
    "key_insights": [
      "The 5m BULLISH_ENTRY at 20.5 is **moderate strength (≈5/10)**: RSI ~52 is neutral, price is just above VWMA20 (20.45)"
    ]
}'''

try:
    result = json.loads(response)
    print("✅ JSON parsed successfully!")
    print(f"Sentiment: {result['sentiment']}")
    print(f"Confidence: {result['confidence']}")
except json.JSONDecodeError as e:
    print(f"❌ JSON parse failed: {e}")
