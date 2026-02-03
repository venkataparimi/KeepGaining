import requests
import json
import sys

def test_local_ai(model="llama3"):
    """
    Test connection to local Ollama instance.
    """
    url = "http://localhost:11434/api/generate"
    
    prompt = """
    You are a quantitative trading expert. 
    Analyze the following market condition:
    "The Nifty 50 index has broken above its 200-day moving average with high volume, but RSI is currently at 75 (overbought)."
    
    Suggest a potential trading strategy with entry and exit criteria.
    """
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    
    print(f"Connecting to local AI ({model})...")
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        
        result = response.json()
        print("\n=== AI Analysis ===")
        print(result.get("response"))
        print("===================\n")
        print(f"Duration: {result.get('total_duration') / 1e9:.2f}s")
        
    except requests.exceptions.ConnectionError:
        print("\n❌ Could not connect to Ollama.")
        print("Make sure Ollama is installed and running ('ollama serve').")
        print("Install command: winget install Ollama.Ollama")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    model = sys.argv[1] if len(sys.argv) > 1 else "llama3"
    test_local_ai(model)
