from typing import List
from app.schemas.broker import OrderRequest, OrderSide
from loguru import logger

class RiskManager:
    """
    Enforces risk limits before orders are sent to the broker.
    """
    def __init__(self):
        self.max_order_value = 100000.0 # Example limit
        self.max_daily_loss = 5000.0
        self.restricted_symbols = ["SCAM_CO"]

    def check_order(self, order: OrderRequest, current_pnl: float = 0.0) -> bool:
        """
        Validate order against risk rules.
        Returns True if safe, False if rejected.
        """
        # 1. Check Restricted Symbols
        if order.symbol in self.restricted_symbols:
            logger.warning(f"Risk Reject: Symbol {order.symbol} is restricted.")
            return False

        # 2. Check Max Order Value (Approximate)
        # Note: We need current price to check value accurately. 
        # For now, assuming price is in order or we skip this check if Market order without price.
        if order.price and (order.quantity * order.price > self.max_order_value):
             logger.warning(f"Risk Reject: Order value exceeds limit {self.max_order_value}")
             return False

        # 3. Check Daily Loss
        if current_pnl < -self.max_daily_loss:
            logger.warning(f"Risk Reject: Max daily loss reached {self.max_daily_loss}")
            return False

        return True
