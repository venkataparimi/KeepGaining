"""
Live Strategy Engine
Real-time indicator computation and strategy execution for live market data.
"""

import asyncio
import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from dataclasses import dataclass
import logging
from datetime import datetime
import json
import redis.asyncio as redis # High-performance in-memory cache

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent / "scripts"))
from indicators_optimized import (
    compute_sma, compute_ema, compute_rsi, compute_supertrend, 
    compute_vwap, compute_bollinger
)

# Configuration
REDIS_URL = "redis://localhost:6379"

@dataclass
class LiveCandle:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

class LiveStrategyEngine:
    def __init__(self):
        self.redis = None
        # In-memory buffer for active symbols: { "NIFTY 50": DataFrame }
        # Only keeps enough history (e.g., 300 rows) for real-time calculation
        self.buffers: Dict[str, pd.DataFrame] = {}
        self.strategies = [] # List of loaded strategy functions

    async def initialize(self):
        self.redis = await redis.from_url(REDIS_URL)
        print("🚀 Live Strategy Engine Initialized")

    async def load_initial_buffer(self, symbol: str, historical_data: pd.DataFrame):
        """Pre-load history so indicators can be computed immediately on first tick."""
        # Keep only necessary columns and last ~500 rows
        buffer = historical_data[['timestamp', 'open', 'high', 'low', 'close', 'volume']].tail(500).copy()
        self.buffers[symbol] = buffer
        print(f"  Loaded buffer for {symbol}: {len(buffer)} candles")

    async def on_new_candle(self, candle: LiveCandle):
        """
        Called EXACTLY when a new 1-minute candle closes.
        """
        symbol = candle.symbol
        
        if symbol not in self.buffers:
            print(f"⚠️ No history for {symbol}, cannot compute indicators.")
            return

        # 1. Update Buffer (Append new candle)
        df = self.buffers[symbol]
        new_row = pd.DataFrame([{
            'timestamp': candle.timestamp,
            'open': candle.open, 
            'high': candle.high, 
            'low': candle.low, 
            'close': candle.close, 
            'volume': candle.volume
        }])
        
        # Efficient concatenation
        df = pd.concat([df, new_row], ignore_index=True)
        
        # Trim buffer to keep it lightweight (max 500 rows)
        if len(df) > 500:
            df = df.iloc[-500:].copy()
            
        self.buffers[symbol] = df
        
        # 2. Compute Indicators (On-the-Fly)
        # We only care about the values for the *latest* candle, but we need history to calculate them.
        # This operation takes < 1ms using numpy vectorization on small (500 row) arrays.
        
        indicators = self._compute_latest_indicators(df)

        # 2b. Save to Database (Optional: Fire and forget task)
        await self._save_indicators_to_db(symbol, indicators)
        
        # 3. Execute Strategies
        await self._evaluate_strategies(symbol, indicators)
        
    def _compute_latest_indicators(self, df: pd.DataFrame) -> Dict:
        """Computes indicators and returns ONLY the latest values as a dict."""
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        volume = df['volume'].values
        
        # We compute full arrays for the buffer, but it's very fast for 500 items
        rsi = compute_rsi(close, 14)[-1]
        sma_200 = compute_sma(close, 200)[-1]
        supertrend, _ = compute_supertrend(high, low, close, 10, 3)
        st_val = supertrend[-1]
        
        return {
            "timestamp": df['timestamp'].iloc[-1],
            "price": close[-1],
            "rsi": rsi,
            "sma_200": sma_200,
            "supertrend": st_val
        }

    async def _evaluate_strategies(self, symbol: str, indicators: Dict):
        """Checks if any strategy conditions are met."""
        
        # Example Strategy: "RSI Reversal" (Placeholder logic)
        # In reality, this would iterate through self.strategies which are dynamically loaded
        
        # Logic: Buy if RSI < 30 (Oversold) AND Price > SuperTrend (Trend is Up)
        if indicators['rsi'] < 30 and indicators['price'] > indicators['supertrend']:
            signal = {
                "strategy": "RSI_Dip_Buy",
                "symbol": symbol,
                "action": "BUY",
                "price": indicators['price'],
                "reason": f"RSI Oversold ({indicators['rsi']:.1f}) in Uptrend"
            }
            print(f"⚡ SIGNAL GENERATED: {signal}")
            
            # Use Local AI to validate signal? (Optional, adds latency but adds intelligence)
            # await self.validate_with_ai(signal)

    async def _save_indicators_to_db(self, symbol: str, indicators: Dict):
        """Persists the computed live indicators to the time-series database."""
        # This should ideally be batched or queued to avoid slowing down the main loop
        # For prototype, we'll just print what would happen
        # In production: await self.db.execute("INSERT INTO indicator_data ...", ...)
        # print(f"  💾 Saved indicators for {symbol} to DB")
        pass

    async def test_live_simulation(self):
        """Simulates a live market feed."""
        print("\n📡 Starting Live Simulation...")
        
        # 1. Load Dummy History
        dates = pd.date_range(end=datetime.now(), periods=500, freq='1min')
        dummy_hist = pd.DataFrame({
            'timestamp': dates,
            'open': 100.0, 'high': 105.0, 'low': 95.0, 'close': 100.0, 'volume': 1000
        })
        await self.load_initial_buffer("NIFTY 50", dummy_hist)
        
        # 2. Simulate Incoming Candles
        for i in range(5):
            await asyncio.sleep(0.5) # Simulate time passing
            
            # Mock candle data
            price = 100 + np.random.randn()
            new_candle = LiveCandle(
                symbol="NIFTY 50",
                timestamp=datetime.now(),
                open=price, high=price+1, low=price-1, close=price, volume=1500
            )
            
            print(f"Tick: {new_candle.timestamp.strftime('%H:%M:%S')} - Price: {new_candle.close:.2f}")
            await self.on_new_candle(new_candle)

if __name__ == "__main__":
    eng = LiveStrategyEngine()
    asyncio.run(eng.initialize())
    asyncio.run(eng.test_live_simulation())
