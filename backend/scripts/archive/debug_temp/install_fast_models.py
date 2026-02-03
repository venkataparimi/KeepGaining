"""
Quick script to pull and test faster Ollama models
"""
import subprocess
import time

FAST_MODELS = [
    {
        'name': 'phi3',
        'size': '3.8B',
        'speed': 'Very Fast',
        'description': 'Microsoft Phi-3 - Excellent for quick responses'
    },
    {
        'name': 'tinyllama',
        'size': '1.1B',
        'speed': 'Extremely Fast',
        'description': 'Tiny but capable - Best for speed'
    },
    {
        'name': 'gemma:2b',
        'size': '2B',
        'speed': 'Very Fast',
        'description': 'Google Gemma 2B - Good balance'
    }
]

def pull_model(model_name):
    """Pull a model from Ollama"""
    print(f"\n📥 Pulling {model_name}...")
    try:
        result = subprocess.run(
            ['ollama', 'pull', model_name],
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode == 0:
            print(f"✅ {model_name} installed successfully!")
            return True
        else:
            print(f"❌ Failed to pull {model_name}: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print(f"⏱️ Timeout pulling {model_name}")
        return False
    except FileNotFoundError:
        print("❌ Ollama command not found. Make sure Ollama is installed.")
        return False

def test_model_speed(model_name):
    """Test model response speed"""
    print(f"\n🧪 Testing {model_name} speed...")
    
    try:
        import requests
        
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
            print(f"✅ Response time: {elapsed:.2f}s")
            print(f"📝 Response: {response.json().get('response', '')[:100]}...")
            return elapsed
        else:
            print(f"❌ Error: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Error testing: {e}")
        return None

if __name__ == "__main__":
    print("=" * 70)
    print("FAST OLLAMA MODELS - INSTALLATION & TESTING")
    print("=" * 70)
    
    print("\n📋 Recommended Fast Models:")
    for i, model in enumerate(FAST_MODELS, 1):
        print(f"\n{i}. {model['name']}")
        print(f"   Size: {model['size']}")
        print(f"   Speed: {model['speed']}")
        print(f"   {model['description']}")
    
    print("\n" + "=" * 70)
    print("INSTALLATION")
    print("=" * 70)
    
    choice = input("\nWhich model to install? (1-3, or 'all'): ").strip()
    
    if choice.lower() == 'all':
        models_to_install = FAST_MODELS
    elif choice in ['1', '2', '3']:
        models_to_install = [FAST_MODELS[int(choice) - 1]]
    else:
        print("Invalid choice. Exiting.")
        exit(1)
    
    # Install models
    installed = []
    for model in models_to_install:
        if pull_model(model['name']):
            installed.append(model['name'])
    
    if not installed:
        print("\n❌ No models were installed successfully.")
        exit(1)
    
    # Test speeds
    print("\n" + "=" * 70)
    print("SPEED TESTING")
    print("=" * 70)
    
    speeds = {}
    for model_name in installed:
        speed = test_model_speed(model_name)
        if speed:
            speeds[model_name] = speed
    
    # Show results
    if speeds:
        print("\n" + "=" * 70)
        print("RESULTS")
        print("=" * 70)
        
        sorted_models = sorted(speeds.items(), key=lambda x: x[1])
        
        print("\n🏆 Models ranked by speed (fastest first):")
        for i, (model, speed) in enumerate(sorted_models, 1):
            print(f"{i}. {model:15} - {speed:.2f}s")
        
        fastest = sorted_models[0][0]
        print(f"\n✨ Fastest model: {fastest}")
        print(f"\n💡 To use in your frontend, update:")
        print(f"   frontend/app/api/ollama/chat/route.ts")
        print(f"   Change: model: 'llama3' → model: '{fastest}'")
    
    print("\n" + "=" * 70)
    print("NEXT STEPS")
    print("=" * 70)
    print("\n1. Update frontend API to use fastest model")
    print("2. Restart your Next.js dev server")
    print("3. Test the AI Assistant - should be much faster!")
