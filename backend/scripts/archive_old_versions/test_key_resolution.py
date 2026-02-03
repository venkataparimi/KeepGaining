#!/usr/bin/env python3
"""Test instrument key resolution."""
import asyncio
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, BACKEND_DIR)

from backfill_all_data import get_instrument_key, build_instrument_key_cache

async def test():
    # Build cache first
    cache = await build_instrument_key_cache()
    
    # Test various symbols
    test_symbols = [
        "RELIANCE",
        "NIFTY 50",
        "NIFTY BANK",
        "BANKNIFTY FUT 30 DEC 25",
        "BANKNIFTY 50800 CE 30 DEC 25",
        "NIFTY 24500 CE 02 JAN 25",  # Expired option
    ]
    
    print("\nTesting instrument key resolution:")
    print("=" * 80)
    for sym in test_symbols:
        key = await get_instrument_key(sym)
        status = "✓" if key else "✗"
        print(f"  {status} {sym}: {key or 'NOT FOUND'}")
    
    print(f"\nCache size: {len(cache)} entries")

if __name__ == '__main__':
    asyncio.run(test())
