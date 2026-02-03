import os
import socket
import sys
import urllib.request
import ssl

def check_dns(hostname):
    print(f"\n--- Checking DNS for {hostname} ---")
    try:
        ip = socket.gethostbyname(hostname)
        print(f"SUCCESS: Resolved {hostname} to {ip}")
        return True
    except Exception as e:
        print(f"FAILURE: Could not resolve {hostname}: {e}")
        return False

def check_env_proxies():
    print("\n--- Checking Proxy Environment Variables ---")
    proxies = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']
    found = False
    for p in proxies:
        val = os.environ.get(p)
        if val:
            print(f"{p}: {val}")
            found = True
        else:
            print(f"{p}: Not Set")
    if not found:
        print("No proxy environment variables found.")

def check_https_connect(url):
    print(f"\n--- Checking HTTPS Connection to {url} ---")
    try:
        req = urllib.request.Request(url)
        # Use a common user agent
        req.add_header('User-Agent', 'Python-Debug-Script/1.0')
        
        # Create a default SSL context
        context = ssl.create_default_context()
        
        with urllib.request.urlopen(req, context=context, timeout=10) as response:
            print(f"SUCCESS: Connected to {url}")
            print(f"Status Code: {response.getcode()}")
            return True
    except urllib.error.URLError as e:
        print(f"FAILURE: Connection error to {url}: {e}")
        if hasattr(e, 'reason'):
            print(f"Reason: {e.reason}")
        return False
    except Exception as e:
        print(f"FAILURE: Unexpected error connecting to {url}: {e}")
        return False

if __name__ == "__main__":
    print("Starting Network Diagnostics...")
    
    # 1. Check Proxies
    check_env_proxies()
    
    # 2. Check DNS
    dns_ok = check_dns("api.openai.com")
    
    # 3. Check Connection (only if DNS worked or we want to try anyway)
    if dns_ok:
        check_https_connect("https://api.openai.com/v1/models")
    else:
        print("Skipping direct connection test due to DNS failure.")
    
    # 4. Check Google as a control
    print("\n--- Control Test (google.com) ---")
    check_dns("google.com")
    check_https_connect("https://www.google.com")
