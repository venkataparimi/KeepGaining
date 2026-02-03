from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum
from app.db.models import OrderSide, OrderStatus, InstrumentType


class OrderType(str, Enum):
    """Order types."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "SL"
    STOP_LOSS_MARKET = "SL-M"


class ProductType(str, Enum):
    """Product types."""
    INTRADAY = "I"
    DELIVERY = "D"
    CNC = "CNC"
    MIS = "MIS"
    NRML = "NRML"


class OrderRequest(BaseModel):
    symbol: str
    quantity: int
    side: OrderSide
    price: Optional[float] = None  # None for Market Order
    order_type: str = "MARKET"  # MARKET, LIMIT, SL, SL-M
    product_type: str = "MIS"  # MIS (Intraday), CNC (Delivery)
    trigger_price: Optional[float] = None
    tag: Optional[str] = None  # Custom tag for identification


class OrderResponse(BaseModel):
    order_id: str
    status: OrderStatus
    message: Optional[str] = None
    filled_quantity: Optional[int] = 0
    average_price: Optional[float] = 0.0


class Position(BaseModel):
    symbol: str
    instrument_key: Optional[str] = None
    quantity: int = 0
    average_price: Optional[float] = 0.0
    last_price: Optional[float] = 0.0
    pnl: Optional[float] = 0.0
    product_type: Optional[str] = "INTRADAY"
    exchange: Optional[str] = None


class Quote(BaseModel):
    symbol: str
    ltp: float = Field(alias="last_price", default=0.0)
    last_price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    volume: int = 0
    timestamp: Optional[datetime] = None
    
    class Config:
        populate_by_name = True
