"""
Instrument Loader Utility
Downloads and parses Upstox master instrument list.
"""
import aiohttp
import gzip
import json
import os
from pathlib import Path
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)

INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
CACHE_FILE = Path(__file__).parent.parent.parent / 'data' / 'complete_instruments.json'

async def download_instruments_file():
    """Download and cache instruments file"""
    if CACHE_FILE.exists():
        # Check staleness (e.g., > 24 hours)? 
        # For now, just use cached if exists to save bandwidth
        return

    logger.info("Downloading instruments file...")
    async with aiohttp.ClientSession() as session:
        async with session.get(INSTRUMENTS_URL) as resp:
            if resp.status == 200:
                content = await resp.read()
                # Decompress
                decompressed = gzip.decompress(content)
                
                # Ensure directory exists
                CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
                
                with open(CACHE_FILE, 'wb') as f:
                    f.write(decompressed)
                logger.info("Instruments file downloaded and cached.")
            else:
                logger.error(f"Failed to download instruments file: {resp.status}")

async def get_stock_keys(symbols: List[str]) -> Dict[str, str]:
    """
    Get instrument keys for a list of stock symbols.
    Returns dict: {symbol: instrument_key}
    """
    await download_instruments_file()
    
    if not CACHE_FILE.exists():
        return {}
    
    mapping = {}
    remaining = set(symbols)
    
    logger.info("Parsing instruments file to resolve keys...")
    
    # The file contains JSON objects line by line? Or one big list?
    # Upstox complete.json is typically a large JSON array or list of objects.
    # We'll read it line by line if appropriate or load it.
    
    # Try reading as JSON list first
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        for item in data:
            if not remaining:
                break
                
            # Upstox keys: NSE_EQ|...
            # We want NSE Equity keys for F&O stocks
            
            # Fields: instrument_key, trading_symbol, exchange, instrument_type
            # Upstox format: exchange='NSE', segment='NSE_EQ' usually.
            is_nse_eq = (item.get('exchange') == 'NSE_EQ' or item.get('segment') == 'NSE_EQ')
            is_equity = (item.get('instrument_type') == 'EQUITY' or item.get('instrument_type') == 'EQ')
            
            if is_nse_eq and is_equity:
                sym = item.get('trading_symbol')
                if sym in remaining:
                    mapping[sym] = item.get('instrument_key')
                    remaining.remove(sym)
                    
    except json.JSONDecodeError:
        # Maybe it's line-delimited JSON?
        logger.warning("Failed to parse as JSON array, trying line-delimited...")
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if not remaining:
                    break
                try:
                    item = json.loads(line)
                    is_nse_eq = (item.get('exchange') == 'NSE_EQ' or item.get('segment') == 'NSE_EQ')
                    is_equity = (item.get('instrument_type') == 'EQUITY' or item.get('instrument_type') == 'EQ')
                    
                    if is_nse_eq and is_equity:
                        sym = item.get('trading_symbol')
                        if sym in remaining:
                            mapping[sym] = item.get('instrument_key')
                            remaining.remove(sym)
                except:
                    continue
                    
    return mapping
