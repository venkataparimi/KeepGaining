"""
Check which symbols are missing from downloads
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.fno_symbols import ALL_SYMBOLS

DATA_DIR = Path("data_downloads")

# Get downloaded files
downloaded = set()
for csv_file in DATA_DIR.glob("*.csv"):
    # Extract symbol from filename: NSE_SYMBOL_EQ.csv -> NSE:SYMBOL-EQ
    name = csv_file.stem  # NSE_SYMBOL_EQ
    parts = name.split("_")
    if len(parts) >= 2:
        exchange = parts[0]
        symbol_part = "_".join(parts[1:])
        # Convert back to Fyers format
        if symbol_part.endswith("_INDEX"):
            symbol = f"{exchange}:{symbol_part.replace('_', '')}-INDEX"
        elif symbol_part.endswith("_EQ"):
            symbol_name = symbol_part[:-3]  # Remove _EQ
            symbol = f"{exchange}:{symbol_name.replace('_', '-')}-EQ"
        else:
            symbol = f"{exchange}:{symbol_part}"
        downloaded.add(symbol)

# Find missing
missing = []
for symbol in ALL_SYMBOLS:
    if symbol not in downloaded:
        missing.append(symbol)

print(f"\nDownloaded: {len(downloaded)}/{len(ALL_SYMBOLS)}")
print(f"Missing: {len(missing)}")

if missing:
    print("\nMissing symbols:")
    for sym in sorted(missing):
        print(f"  - {sym}")
