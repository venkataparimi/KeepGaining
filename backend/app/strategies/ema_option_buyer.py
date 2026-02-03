from datetime import datetime
from typing import Any, Dict, List, Optional
from app.strategies.base import BaseStrategy
from app.schemas.broker import OrderRequest, OrderResponse, OrderSide, OrderStatus
from loguru import logger
import pandas as pd
import asyncio

class EMAOptionBuyingStrategy(BaseStrategy):
    """
    EMA Option Buying Strategy:
    - Timeframe: 5 minutes (default).
    - Indicators: Fast EMA (9) and Slow EMA (21) on Underlying.
    - Signal:
        - Fast crosses ABOVE Slow -> Buy ATM Call (CE).
        - Fast crosses BELOW Slow -> Buy ATM Put (PE).
    - Risk Management:
        - Stop Loss: 10% of Premium.
        - Target: 20% of Premium (1:2 Risk-Reward).
    """

    def __init__(self, broker, data_feed, config: Dict[str, Any]):
        super().__init__(broker, data_feed, config)
        self.underlying = config.get("underlying", "NSE:NIFTY50-INDEX")
        self.fast_ema_period = config.get("fast_ema", 9)
        self.slow_ema_period = config.get("slow_ema", 21)
        self.quantity = config.get("quantity", 50)
        self.expiry_date = config.get("expiry_date") # e.g., "23NOV"
        self.sl_pct = config.get("sl_percentage", 0.10)
        self.target_pct = config.get("target_percentage", 0.20)
        
        self.candles = pd.DataFrame()
        self.current_position = None # "CE" or "PE" or None
        self.entry_price = 0.0
        self.active_symbol = None

    async def on_start(self):
        logger.info(f"EMAOptionBuyingStrategy started for {self.underlying}")
        # Warmup: Fetch historical data to calculate initial EMAs
        end_date = datetime.now()
        start_date = end_date - pd.Timedelta(days=5)
        
        try:
            df = await self.broker.get_historical_data(
                symbol=self.underlying,
                resolution="5", # 5 minute
                start_date=start_date,
                end_date=end_date
            )
            if not df.empty:
                self.candles = df
                self.calculate_indicators()
                logger.info(f"Warmed up with {len(df)} candles.")
        except Exception as e:
            logger.error(f"Failed to warmup strategy: {e}")

    async def on_stop(self):
        logger.info("EMAOptionBuyingStrategy stopped.")

    async def on_tick(self, tick: Any):
        # We primarily use candles, but can use ticks for SL/Target monitoring if needed
        pass

    async def on_order_update(self, order: OrderResponse):
        """Handle order updates from broker"""
        logger.info(f"Order Update: {order.order_id} - Status: {order.status}")
        # Can implement SL/Target monitoring logic here
        pass

    async def on_candle(self, candle: Any):
        """
        candle expected to be a dict or object with: timestamp, open, high, low, close, volume
        """
        # Append new candle
        new_row = pd.DataFrame([candle])
        self.candles = pd.concat([self.candles, new_row], ignore_index=True)
        
        # Keep only last 100 candles to save memory
        if len(self.candles) > 100:
            self.candles = self.candles.iloc[-100:].reset_index(drop=True)
            
        self.calculate_indicators()
        await self.check_signals()

    def calculate_indicators(self):
        if len(self.candles) < self.slow_ema_period:
            return

        self.candles['fast_ema'] = self.candles['close'].ewm(span=self.fast_ema_period, adjust=False).mean()
        self.candles['slow_ema'] = self.candles['close'].ewm(span=self.slow_ema_period, adjust=False).mean()

    async def check_signals(self):
        if len(self.candles) < 2:
            return

        # Get last two rows
        prev = self.candles.iloc[-2]
        curr = self.candles.iloc[-1]

        # Check Crossover
        crossover_up = prev['fast_ema'] <= prev['slow_ema'] and curr['fast_ema'] > curr['slow_ema']
        crossover_down = prev['fast_ema'] >= prev['slow_ema'] and curr['fast_ema'] < curr['slow_ema']

        if crossover_up:
            logger.info("Signal: Fast EMA crossed ABOVE Slow EMA (Bullish)")
            await self.enter_position("CE", curr['close'])
            
        elif crossover_down:
            logger.info("Signal: Fast EMA crossed BELOW Slow EMA (Bearish)")
            await self.enter_position("PE", curr['close'])

    async def enter_position(self, side: str, spot_price: float):
        # 1. Close existing position if any (Reversal)
        if self.current_position:
            await self.exit_position("Signal Reversal")

        # 2. Select Strike (ATM)
        strike_step = 50 if "NIFTY" in self.underlying else 100
        atm_strike = round(spot_price / strike_step) * strike_step
        
        symbol_prefix = "NIFTY" if "NIFTY" in self.underlying else "BANKNIFTY"
        if not self.expiry_date:
            logger.error("Expiry date missing")
            return

        self.active_symbol = f"NSE:{symbol_prefix}{self.expiry_date}{atm_strike}{side}"
        
        # 3. Place Buy Order
        logger.info(f"Buying {self.active_symbol} (ATM {side})")
        try:
            order = OrderRequest(
                symbol=self.active_symbol,
                quantity=self.quantity,
                side=OrderSide.BUY,
                order_type="MARKET",
                product_type="MIS"
            )
            resp = await self.broker.place_order(order)
            
            if resp.status == OrderStatus.PENDING or resp.status == OrderStatus.FILLED:
                self.current_position = side
                # Ideally fetch fill price from order update or quote
                # For now, fetch quote
                await asyncio.sleep(1)
                quote = await self.broker.get_quote(self.active_symbol)
                self.entry_price = quote.last_price
                logger.info(f"Entered {side} at {self.entry_price}")
                
                # Place SL/Target (Logic only, or place real orders)
                # Here we will just log targets
                sl_price = self.entry_price * (1 - self.sl_pct)
                tgt_price = self.entry_price * (1 + self.target_pct)
                logger.info(f"SL: {sl_price}, Target: {tgt_price}")
                
        except Exception as e:
            logger.error(f"Entry failed: {e}")

    async def exit_position(self, reason: str):
        if not self.active_symbol:
            return

        logger.info(f"Exiting position {self.active_symbol}. Reason: {reason}")
        try:
            order = OrderRequest(
                symbol=self.active_symbol,
                quantity=self.quantity,
                side=OrderSide.SELL, # Sell to close Buy
                order_type="MARKET",
                product_type="MIS"
            )
            await self.broker.place_order(order)
            self.current_position = None
            self.active_symbol = None
            self.entry_price = 0.0
        except Exception as e:
            logger.error(f"Exit failed: {e}")
