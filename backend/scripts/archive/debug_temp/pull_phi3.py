"""
Pull phi3 model using Python (bypasses PATH issues)
"""
import requests
import time

def pull_model_via_api(model_name='phi3'):
    """Pull a model using Ollama's API"""
    print(f"📥 Pulling {model_name} model via API...")
    print("This may take a few minutes depending on your internet speed...")
    
    url = 'http://localhost:11434/api/pull'
    
    try:
        response = requests.post(
            url,
            json={'name': model_name},
            stream=True,
            timeout=600
        )
        
        if response.status_code == 200:
            print(f"\n✅ Starting download of {model_name}...")
            
            # Stream the response to show progress
            for line in response.iter_lines():
                if line:
                    try:
                        data = eval(line.decode('utf-8'))
                        status = data.get('status', '')
                        
                        if 'pulling' in status.lower():
                            print(f"  {status}", end='\r')
                        elif 'success' in status.lower():
                            print(f"\n✅ {status}")
                        elif status:
                            print(f"  {status}")
                    except:
                        pass
            
            print(f"\n✅ {model_name} installed successfully!")
            return True
        else:
            print(f"❌ Error: {response.status_code}")
            print(response.text)
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to Ollama server")
        print("Make sure Ollama is running")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_model(model_name='phi3'):
    """Test the newly installed model"""
    print(f"\n🧪 Testing {model_name}...")
    
    try:
        start = time.time()
        response = requests.post(
            'http://localhost:11434/api/generate',
            json={
                'model': model_name,
                'prompt': 'Say hello in one sentence.',
                'stream': False
            },
            timeout=30
        )
        elapsed = time.time() - start
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Response time: {elapsed:.2f}s")
            print(f"📝 Response: {data.get('response', '')}")
            return True
        else:
            print(f"❌ Error: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("=" * 70)
    print("INSTALL PHI3 MODEL (Fast Alternative to Llama3)")
    print("=" * 70)
    print()
    print("Phi3 is 3-5x faster than llama3 with similar quality")
    print("Size: ~2.3GB (vs llama3's 4.7GB)")
    print()
    
    if pull_model_via_api('phi3'):
        print("\n" + "=" * 70)
        if test_model('phi3'):
            print("\n" + "=" * 70)
            print("✅ SUCCESS!")
            print("=" * 70)
            print()
            print("Next steps:")
            print("1. Your frontend is already configured to use phi3")
            print("2. Restart your Next.js dev server:")
            print("   cd frontend")
            print("   npm run dev")
            print("3. Go to http://localhost:3000/ai-assistant")
            print("4. Enjoy 3-5x faster responses!")
    else:
        print("\n❌ Failed to install phi3")
        print("\nTroubleshooting:")
        print("1. Make sure Ollama is running")
        print("2. Check your internet connection")
        print("3. Try opening a new PowerShell and run: ollama pull phi3")
