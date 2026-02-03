import requests
import json
import sys

def ask_ollama(prompt, model="llama3"):
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        result = response.json()
        print("=== Ollama Response ===")
        print(result.get("response", ""))
        print("=======================")
        print(f"Duration: {result.get('total_duration',0)/1e9:.2f}s")
        return result
    except Exception as e:
        print(f"Error contacting Ollama: {e}")
        return None

if __name__ == "__main__":
    # Prompt to ask about IEX historical data availability
    prompt = """
You are a knowledgeable data engineer. Please answer concisely:

Is historical stock price data available from the IEX Cloud API? If so, what is the earliest date for which US equity data can be retrieved? Mention any limits or notes.
"""
    model = sys.argv[1] if len(sys.argv) > 1 else "llama3"
    result = ask_ollama(prompt, model)
    # If the response is empty, inform the user
    if not result or not result.get("response"):
        print("⚠️ No response received. The model may not have knowledge about IEX Cloud.")
