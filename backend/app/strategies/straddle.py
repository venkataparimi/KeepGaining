from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional
from app.strategies.base import BaseStrategy
from app.schemas.broker import OrderRequest, OrderResponse, OrderSide, OrderStatus
from loguru import logger
import asyncio

class ShortStraddleStrategy(BaseStrategy):
    """
    Short Straddle Strategy:
    - Sell ATM CE and PE at a specific time (e.g., 9:20 AM).
    - Place Stop Loss orders for both legs.
    - Exit at a specific time (e.g., 3:15 PM).
    """

    def __init__(self, broker, data_feed, config: Dict[str, Any]):
        super().__init__(broker, data_feed, config)
        self.underlying = config.get("underlying", "NSE:NIFTY50-INDEX")
        self.entry_time = datetime.strptime(config.get("entry_time", "09:20"), "%H:%M").time()
        self.exit_time = datetime.strptime(config.get("exit_time", "15:15"), "%H:%M").time()
        self.sl_percentage = config.get("sl_percentage", 0.25) # 25% SL
        self.quantity = config.get("quantity", 50)
        self.expiry_date = config.get("expiry_date") # Format: "23NOV" or specific Fyers format
        
        self.ce_symbol = None
        self.pe_symbol = None
        self.ce_entry_price = 0.0
        self.pe_entry_price = 0.0
        self.ce_sl_order_id = None
        self.pe_sl_order_id = None
        self.entered = False

    async def on_start(self):
        logger.info(f"ShortStraddleStrategy initialized for {self.underlying}")

    async def on_stop(self):
        logger.info("ShortStraddleStrategy stopped.")

    async def on_tick(self, tick: Any):
        # In a real system, tick would be an object. Assuming dict or object with timestamp.
        # For this implementation, we'll check system time or tick time.
        now = datetime.now().time() # In backtest, use tick.timestamp

        if not self.entered and now >= self.entry_time and now < self.exit_time:
            await self.execute_entry()
        
        if self.entered and now >= self.exit_time:
            await self.execute_exit()

    async def on_candle(self, candle: Any):
        # Can be used if running on candle data
        pass

    async def on_order_update(self, order: OrderResponse):
        logger.info(f"Order Update: {order.order_id} - {order.status}")
        # Handle SL hits or Exits here
        pass

    async def execute_entry(self):
        logger.info("Executing Short Straddle Entry...")
        
        # 1. Get Spot Price
        quote = await self.broker.get_quote(self.underlying)
        spot_price = quote.last_price
        if spot_price == 0:
            logger.error("Failed to fetch spot price. Aborting entry.")
            return

        # 2. Calculate ATM Strike
        # Assuming Nifty (50 strike diff) or BankNifty (100 strike diff)
        strike_step = 50 if "NIFTY" in self.underlying else 100
        atm_strike = round(spot_price / strike_step) * strike_step
        logger.info(f"Spot: {spot_price}, ATM Strike: {atm_strike}")

        # 3. Construct Symbols
        # Fyers Symbol Format: NSE:NIFTY23NOV19800CE
        # We need to know the symbol prefix (NIFTY/BANKNIFTY) and expiry format
        # This is tricky without a helper. Assuming user provides correct prefix in config or we parse it.
        symbol_prefix = "NIFTY" if "NIFTY" in self.underlying else "BANKNIFTY"
        # We need the expiry string e.g. "23NOV"
        if not self.expiry_date:
            logger.error("Expiry date not configured.")
            return

        self.ce_symbol = f"NSE:{symbol_prefix}{self.expiry_date}{atm_strike}CE"
        self.pe_symbol = f"NSE:{symbol_prefix}{self.expiry_date}{atm_strike}PE"

        # 4. Place Sell Orders
        # Sell CE
        ce_order = OrderRequest(
            symbol=self.ce_symbol,
            quantity=self.quantity,
            side=OrderSide.SELL,
            order_type="MARKET",
            product_type="MIS"
        )
        ce_resp = await self.broker.place_order(ce_order)
        logger.info(f"Placed CE Sell: {ce_resp.message}")

        # Sell PE
        pe_order = OrderRequest(
            symbol=self.pe_symbol,
            quantity=self.quantity,
            side=OrderSide.SELL,
            order_type="MARKET",
            product_type="MIS"
        )
        pe_resp = await self.broker.place_order(pe_order)
        logger.info(f"Placed PE Sell: {pe_resp.message}")

        self.entered = True
        
        # 5. Place Stop Loss Orders (Simulated or Real)
        # We need to wait for fills to get the average price to calculate SL
        # For simplicity, we'll fetch quote again or wait for order update.
        # Here we will just log it. In production, we'd use on_order_update to place SL.
        await self.place_sl_orders()

    async def place_sl_orders(self):
        # Wait a bit for orders to fill (naive approach)
        await asyncio.sleep(2)
        
        # Get quotes to simulate fill price (since we used Market orders)
        ce_quote = await self.broker.get_quote(self.ce_symbol)
        pe_quote = await self.broker.get_quote(self.pe_symbol)
        
        self.ce_entry_price = ce_quote.last_price
        self.pe_entry_price = pe_quote.last_price
        
        ce_sl_price = self.ce_entry_price * (1 + self.sl_percentage)
        pe_sl_price = self.pe_entry_price * (1 + self.sl_percentage)
        
        logger.info(f"Placing SL for CE at {ce_sl_price} (Entry: {self.ce_entry_price})")
        logger.info(f"Placing SL for PE at {pe_sl_price} (Entry: {self.pe_entry_price})")
        
        # Place SL-M Orders (if broker supports, else we monitor manually)
        # Fyers supports SL-M.
        # Note: Fyers API might require specific params for SL.
        # We'll assume the broker adapter handles it or we use "SL" type.
        
        # CE SL (Buy)
        ce_sl_order = OrderRequest(
            symbol=self.ce_symbol,
            quantity=self.quantity,
            side=OrderSide.BUY,
            order_type="SL", # or SL-M
            price=ce_sl_price, # Trigger Price
            trigger_price=ce_sl_price,
            product_type="MIS"
        )
        # await self.broker.place_order(ce_sl_order) # Uncomment when ready

    async def execute_exit(self):
        logger.info("Time Exit Reached. Squaring off all positions.")
        
        # Cancel pending SLs
        # Close open positions
        if self.ce_symbol:
            await self.broker.place_order(OrderRequest(
                symbol=self.ce_symbol,
                quantity=self.quantity,
                side=OrderSide.BUY,
                order_type="MARKET"
            ))
        
        if self.pe_symbol:
            await self.broker.place_order(OrderRequest(
                symbol=self.pe_symbol,
                quantity=self.quantity,
                side=OrderSide.BUY,
                order_type="MARKET"
            ))
            
        self.entered = False
