"""
Pydantic Schemas - Trading
KeepGaining Trading Platform

API schemas for:
- Strategies
- Orders
- Trades
- Positions
"""

from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional, List, Any, Dict
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


# =============================================================================
# Base Schemas
# =============================================================================

class BaseSchema(BaseModel):
    """Base schema with common configuration."""
    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Strategy Schemas
# =============================================================================

class StrategyConfigBase(BaseSchema):
    """Base strategy config fields."""
    strategy_name: str = Field(..., max_length=100)
    strategy_type: str = Field(..., max_length=50)  # INTRADAY, SWING, POSITIONAL
    description: Optional[str] = None
    version: str = "1.0.0"
    
    # Trading Parameters
    instruments: Optional[Dict[str, Any]] = None
    timeframes: Optional[List[str]] = None
    entry_time_start: Optional[time] = None
    entry_time_end: Optional[time] = None
    exit_time: Optional[time] = None
    
    # Risk Parameters
    max_positions: int = 5
    position_size_type: str = "FIXED"
    position_size_value: Optional[Decimal] = None
    default_sl_percent: Optional[Decimal] = None
    default_target_percent: Optional[Decimal] = None
    max_loss_per_day: Optional[Decimal] = None
    max_loss_per_trade: Optional[Decimal] = None
    trailing_sl_enabled: bool = False
    trailing_sl_percent: Optional[Decimal] = None
    
    # Execution
    order_type: str = "MARKET"
    product_type: str = "INTRADAY"
    
    # Status
    is_active: bool = False
    is_paper_trading: bool = True


class StrategyConfigCreate(StrategyConfigBase):
    """Schema for creating strategy."""
    pass


class StrategyConfigUpdate(BaseSchema):
    """Schema for updating strategy."""
    strategy_name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    instruments: Optional[Dict[str, Any]] = None
    timeframes: Optional[List[str]] = None
    max_positions: Optional[int] = None
    default_sl_percent: Optional[Decimal] = None
    default_target_percent: Optional[Decimal] = None
    is_active: Optional[bool] = None
    is_paper_trading: Optional[bool] = None


class StrategyConfigResponse(StrategyConfigBase):
    """Schema for strategy response."""
    strategy_id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# =============================================================================
# Strategy Definition Schemas
# =============================================================================

class StrategyCondition(BaseSchema):
    """Single strategy condition."""
    indicator: str  # e.g., "rsi_14", "ema_21"
    operator: str  # "gt", "lt", "eq", "gte", "lte", "crosses_above", "crosses_below"
    value: Optional[float] = None  # Static value
    compare_to: Optional[str] = None  # Another indicator


class StrategyDefinitionBase(BaseSchema):
    """Base strategy definition fields."""
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    version: int = 1
    
    # Trading Parameters
    instrument_types: Optional[List[str]] = None
    allowed_instruments: Optional[List[str]] = None
    timeframes: List[str]
    trading_sessions: Optional[Dict[str, Any]] = None
    
    # Entry/Exit Conditions
    entry_conditions: Dict[str, Any]
    entry_logic: Optional[str] = None
    exit_conditions: Dict[str, Any]
    exit_logic: Optional[str] = None
    
    # Risk Overrides
    default_sl_percent: Optional[Decimal] = None
    default_target_percent: Optional[Decimal] = None
    max_positions: Optional[int] = None
    position_size_type: Optional[str] = None
    position_size_value: Optional[Decimal] = None
    
    # Metadata
    tags: Optional[List[str]] = None
    is_active: bool = False


class StrategyDefinitionCreate(StrategyDefinitionBase):
    """Schema for creating definition."""
    strategy_id: UUID


class StrategyDefinitionUpdate(BaseSchema):
    """Schema for updating definition."""
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    entry_conditions: Optional[Dict[str, Any]] = None
    exit_conditions: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class StrategyDefinitionResponse(StrategyDefinitionBase):
    """Schema for definition response."""
    definition_id: UUID
    strategy_id: UUID
    backtested: bool = False
    backtest_results: Optional[Dict[str, Any]] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# =============================================================================
# Order Schemas
# =============================================================================

class OrderBase(BaseSchema):
    """Base order fields."""
    order_type: str = Field(..., max_length=20)  # MARKET, LIMIT, SL, SL-M
    side: str = Field(..., max_length=4)  # BUY, SELL
    product_type: str = Field(..., max_length=20)  # INTRADAY, DELIVERY
    quantity: int = Field(..., ge=1)
    price: Optional[Decimal] = None
    trigger_price: Optional[Decimal] = None


class OrderCreate(OrderBase):
    """Schema for creating order."""
    strategy_id: Optional[UUID] = None
    instrument_id: UUID


class OrderUpdate(BaseSchema):
    """Schema for updating order."""
    price: Optional[Decimal] = None
    trigger_price: Optional[Decimal] = None
    quantity: Optional[int] = Field(None, ge=1)


class OrderResponse(OrderBase):
    """Schema for order response."""
    order_id: UUID
    strategy_id: Optional[UUID] = None
    instrument_id: UUID
    
    # Broker
    broker_name: Optional[str] = None
    broker_order_id: Optional[str] = None
    exchange_order_id: Optional[str] = None
    
    # Status
    status: str
    filled_quantity: int = 0
    average_price: Optional[Decimal] = None
    rejection_reason: Optional[str] = None
    
    # Timestamps
    placed_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class OrderWithInstrument(OrderResponse):
    """Order with instrument details."""
    trading_symbol: str
    exchange: str


# =============================================================================
# Trade Schemas
# =============================================================================

class TradeBase(BaseSchema):
    """Base trade fields."""
    side: str = Field(..., max_length=4)
    quantity: int = Field(..., ge=1)
    price: Decimal


class TradeCreate(TradeBase):
    """Schema for creating trade."""
    order_id: UUID
    strategy_id: Optional[UUID] = None
    instrument_id: UUID
    executed_at: datetime
    broker_name: Optional[str] = None
    broker_trade_id: Optional[str] = None


class TradeResponse(TradeBase):
    """Schema for trade response."""
    trade_id: UUID
    order_id: UUID
    strategy_id: Optional[UUID] = None
    instrument_id: UUID
    broker_name: Optional[str] = None
    broker_trade_id: Optional[str] = None
    exchange_trade_id: Optional[str] = None
    executed_at: datetime
    created_at: Optional[datetime] = None


# =============================================================================
# Position Schemas
# =============================================================================

class PositionBase(BaseSchema):
    """Base position fields."""
    side: str = Field(..., max_length=5)  # LONG, SHORT
    quantity: int = Field(..., ge=1)
    average_entry_price: Decimal


class PositionCreate(PositionBase):
    """Schema for creating position."""
    strategy_id: Optional[UUID] = None
    instrument_id: UUID
    opened_at: datetime
    stop_loss: Optional[Decimal] = None
    target: Optional[Decimal] = None


class PositionUpdate(BaseSchema):
    """Schema for updating position."""
    current_price: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    target: Optional[Decimal] = None
    trailing_sl: Optional[Decimal] = None
    quantity: Optional[int] = Field(None, ge=0)


class PositionResponse(PositionBase):
    """Schema for position response."""
    position_id: UUID
    strategy_id: Optional[UUID] = None
    instrument_id: UUID
    
    # Current State
    current_price: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    target: Optional[Decimal] = None
    trailing_sl: Optional[Decimal] = None
    
    # P&L
    unrealized_pnl: Optional[Decimal] = None
    realized_pnl: Decimal = Decimal("0")
    
    # Status
    status: str
    opened_at: datetime
    closed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PositionWithInstrument(PositionResponse):
    """Position with instrument details."""
    trading_symbol: str
    exchange: str
    lot_size: int


# =============================================================================
# P&L Schemas
# =============================================================================

class DailyPnLBase(BaseSchema):
    """Base daily P&L fields."""
    date: date
    gross_pnl: Decimal = Decimal("0")
    brokerage: Decimal = Decimal("0")
    taxes: Decimal = Decimal("0")
    net_pnl: Decimal = Decimal("0")
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0


class DailyPnLCreate(DailyPnLBase):
    """Schema for creating daily P&L."""
    strategy_id: Optional[UUID] = None
    max_drawdown: Optional[Decimal] = None
    max_profit: Optional[Decimal] = None
    opening_capital: Optional[Decimal] = None
    closing_capital: Optional[Decimal] = None


class DailyPnLResponse(DailyPnLBase):
    """Schema for daily P&L response."""
    pnl_id: UUID
    strategy_id: Optional[UUID] = None
    max_drawdown: Optional[Decimal] = None
    max_profit: Optional[Decimal] = None
    opening_capital: Optional[Decimal] = None
    closing_capital: Optional[Decimal] = None
    win_rate: Optional[float] = None
    
    @property
    def win_rate_calculated(self) -> Optional[float]:
        """Calculate win rate."""
        if self.total_trades > 0:
            return (self.winning_trades / self.total_trades) * 100
        return None


class PnLSummary(BaseSchema):
    """P&L summary across multiple days."""
    start_date: date
    end_date: date
    total_gross_pnl: Decimal
    total_net_pnl: Decimal
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_profit: Optional[Decimal] = None
    avg_loss: Optional[Decimal] = None
    profit_factor: Optional[float] = None
    max_drawdown: Optional[Decimal] = None
    sharpe_ratio: Optional[float] = None
