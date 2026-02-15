import requests
import asyncio
from datetime import datetime, timedelta

def test_historical_data():
    base_url = "http://127.0.0.1:8001/api/historical-data/"
    
    # Test valid request
    params = {
        'symbol': 'NIFTY 50', # Ensure this symbol exists in DB or pick one that does
        "instrument_type": "INDEX",
        "time_frame": "1d",
        "indicators": ["sma", "rsi"],
        "start_date": (datetime.now() - timedelta(days=7)).isoformat()
    }
    
    print(f"Testing {base_url} with params: {params}")
    try:
        response = requests.get(base_url, params=params)
        with open("verification_result.txt", "w") as f:
            f.write(f"Status Code: {response.status_code}\n")
            if response.status_code == 200:
                data = response.json()
                f.write(f"Received {len(data)} candles\n")
                if data:
                    f.write(f"First candle: {data[0]}\n")
                    f.write(f"Last candle: {data[-1]}\n")
            else:
                f.write(f"Error: {response.text}\n")
    except Exception as e:
        with open("verification_result.txt", "w") as f:
            f.write(f"Request failed: {e}\n")

if __name__ == "__main__":
    test_historical_data()
