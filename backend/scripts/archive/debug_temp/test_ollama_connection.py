"""
Test if Ollama is accessible and pull model if needed
"""
import requests
import json

def test_ollama_connection():
    """Test if Ollama server is running"""
    try:
        response = requests.get('http://localhost:11434/api/tags')
        if response.status_code == 200:
            print("✅ Ollama server is running!")
            models = response.json().get('models', [])
            if models:
                print(f"\n📦 Installed models:")
                for model in models:
                    print(f"  - {model['name']}")
                return True
            else:
                print("\n⚠️  No models installed yet")
                print("\nTo install llama3:")
                print("1. Open a new PowerShell window")
                print("2. Run: ollama pull llama3")
                return False
        else:
            print(f"❌ Unexpected response: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to Ollama server")
        print("\nOllama might not be running. Try:")
        print("1. Open a new PowerShell window")
        print("2. Run: ollama serve")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_ollama_query():
    """Test a simple query"""
    try:
        url = 'http://localhost:11434/api/generate'
        payload = {
            'model': 'llama3',
            'prompt': 'Say "Ollama is working!" in one sentence.',
            'stream': False
        }
        
        print("\n🤖 Testing Ollama with a simple query...")
        response = requests.post(url, json=payload)
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Response: {result.get('response', '')}")
            return True
        elif response.status_code == 404:
            print("❌ Model 'llama3' not found")
            print("\nInstall it with: ollama pull llama3")
            return False
        else:
            print(f"❌ Error {response.status_code}: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("="*70)
    print("OLLAMA CONNECTION TEST")
    print("="*70)
    print()
    
    if test_ollama_connection():
        test_ollama_query()
    
    print("\n" + "="*70)
    print("NEXT STEPS")
    print("="*70)
    print()
    print("If models are installed:")
    print("  python backend/scripts/ollama_quickstart.py")
    print()
    print("If no models:")
    print("  1. Open new PowerShell")
    print("  2. Run: ollama pull llama3")
    print("  3. Then run: python backend/scripts/ollama_quickstart.py")
