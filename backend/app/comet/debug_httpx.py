import httpx
import os
import sys

def test_httpx():
    print("Testing httpx connectivity...")
    url = "https://api.openai.com/v1/models"
    
    try:
        # Test 1: Default Client
        print("\n--- Test 1: Default httpx.Client ---")
        with httpx.Client() as client:
            resp = client.get(url, timeout=10)
            print(f"Response: {resp.status_code}")
            
    except Exception as e:
        print(f"Test 1 Failed: {e}")

    try:
        # Test 2: Trust Env = True (Explicit)
        print("\n--- Test 2: Trust Env = True ---")
        with httpx.Client(trust_env=True) as client:
            resp = client.get(url, timeout=10)
            print(f"Response: {resp.status_code}")
            
    except Exception as e:
        print(f"Test 2 Failed: {e}")

    try:
        # Test 3: Trust Env = False
        print("\n--- Test 3: Trust Env = False ---")
        with httpx.Client(trust_env=False) as client:
            resp = client.get(url, timeout=10)
            print(f"Response: {resp.status_code}")
            
    except Exception as e:
        print(f"Test 3 Failed: {e}")

if __name__ == "__main__":
    test_httpx()
