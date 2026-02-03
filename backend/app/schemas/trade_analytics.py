"""
Trade Analytics Schemas
Comprehensive trade-level tracking with multi-dimensional data
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class TradeDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class StopLossType(str, Enum):
    FIXED = "FIXED"           # Fixed price SL
    PERCENTAGE = "PERCENTAGE"  # % from entry
    ATR_BASED = "ATR_BASED"   # ATR multiplier
    TRAILING = "TRAILING"     # Trailing SL
    NONE = "NONE"


class TradeStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"


# =============================================================================
# Entry Context - Captured at Trade Entry
# =============================================================================

class EntryContext(BaseModel):
    """Context captured at the moment of trade entry."""
    
    # Spot/Underlying data
    spot_price: float = Field(description="Underlying spot price at entry")
    spot_change_percent: Optional[float] = Field(None, description="Spot % change for the day at entry")
    
    # Option-specific data (if applicable)
    strike_price: Optional[float] = None
    option_type: Optional[str] = None  # CE/PE
    expiry_date: Optional[str] = None
    days_to_expiry: Optional[int] = None
    moneyness: Optional[str] = None  # ITM/ATM/OTM
    distance_from_atm: Optional[float] = Field(None, description="% distance from ATM strike")
    
    # Greeks at entry
    iv_at_entry: Optional[float] = Field(None, description="Implied Volatility at entry")
    delta_at_entry: Optional[float] = None
    gamma_at_entry: Optional[float] = None
    theta_at_entry: Optional[float] = None
    vega_at_entry: Optional[float] = None
    
    # Market context
    vix_at_entry: Optional[float] = Field(None, description="India VIX at entry")
    market_trend: Optional[str] = Field(None, description="BULLISH/BEARISH/SIDEWAYS")
    sector_trend: Optional[str] = None
    
    # Technical indicators at entry
    rsi_at_entry: Optional[float] = None
    macd_signal: Optional[str] = None  # BULLISH/BEARISH/NEUTRAL
    support_level: Optional[float] = None
    resistance_level: Optional[float] = None
    
    # Volume context
    volume_ratio: Optional[float] = Field(None, description="Volume vs average volume ratio")
    oi_change_percent: Optional[float] = Field(None, description="OI change % at entry")


class StopLossConfig(BaseModel):
    """Stop loss configuration and tracking."""
    
    sl_type: StopLossType = StopLossType.NONE
    initial_sl_price: Optional[float] = None
    current_sl_price: Optional[float] = None
    sl_percentage: Optional[float] = Field(None, description="SL as % from entry")
    sl_points: Optional[float] = Field(None, description="SL in absolute points")
    
    # Trailing SL specific
    trailing_activated: bool = False
    trailing_trigger_price: Optional[float] = Field(None, description="Price at which trailing starts")
    trailing_distance: Optional[float] = Field(None, description="Trailing distance in points or %")
    trailing_step: Optional[float] = Field(None, description="Step size for trailing adjustment")
    highest_price_since_entry: Optional[float] = None
    lowest_price_since_entry: Optional[float] = None
    
    # SL history
    sl_adjustments: List[Dict[str, Any]] = Field(default_factory=list, description="History of SL changes")


class TargetConfig(BaseModel):
    """Target/Take profit configuration."""
    
    target_price: Optional[float] = None
    target_percentage: Optional[float] = Field(None, description="Target as % from entry")
    partial_targets: List[Dict[str, float]] = Field(
        default_factory=list, 
        description="List of {price: qty_percent} for partial exits"
    )
    risk_reward_ratio: Optional[float] = None


# =============================================================================
# Recommended Stop Loss
# =============================================================================

class StopLossRecommendation(BaseModel):
    """AI/Rule-based stop loss recommendations."""
    
    # Different SL methods
    atr_based_sl: Optional[float] = Field(None, description="SL based on ATR (1.5x ATR)")
    percentage_sl: Optional[float] = Field(None, description="Standard % based SL")
    support_based_sl: Optional[float] = Field(None, description="SL below support level")
    swing_low_sl: Optional[float] = Field(None, description="SL below recent swing low")
    
    # Recommended SL
    recommended_sl: float = Field(description="Best recommended SL price")
    recommended_sl_type: StopLossType = Field(description="Recommended SL type")
    sl_risk_amount: float = Field(description="Max loss if SL hits")
    sl_risk_percent: float = Field(description="Max loss as % of position value")
    
    # Confidence and reasoning
    confidence: float = Field(ge=0, le=1, description="Confidence in recommendation")
    reasoning: str = Field(description="Explanation for the recommendation")
    
    # Historical context
    historical_sl_hit_rate: Optional[float] = Field(
        None, 
        description="% of similar trades that hit this SL level"
    )


# =============================================================================
# Current Trade State
# =============================================================================

class CurrentTradeState(BaseModel):
    """Real-time state of the trade."""
    
    # Current prices
    current_ltp: float
    current_spot_price: float
    
    # P&L
    unrealized_pnl: float
    unrealized_pnl_percent: float
    max_profit_seen: float = Field(description="Highest unrealized P&L during trade")
    max_drawdown_seen: float = Field(description="Lowest unrealized P&L during trade")
    
    # Current Greeks (for options)
    current_iv: Optional[float] = None
    current_delta: Optional[float] = None
    current_theta: Optional[float] = None
    iv_change: Optional[float] = Field(None, description="IV change since entry")
    
    # Time decay impact
    theta_decay_impact: Optional[float] = Field(None, description="Estimated theta decay since entry")
    
    # Price movement
    price_change_percent: float
    spot_change_since_entry: float
    
    # Risk status
    sl_distance_percent: Optional[float] = Field(None, description="Distance to SL as %")
    target_distance_percent: Optional[float] = Field(None, description="Distance to target as %")
    risk_reward_current: Optional[float] = Field(None, description="Current risk:reward ratio")


# =============================================================================
# Trade Analytics Response
# =============================================================================

class TradeAnalytics(BaseModel):
    """Complete trade analytics for a position."""
    
    # Trade identification
    trade_id: str
    symbol: str
    tradingsymbol: Optional[str] = None
    underlying: Optional[str] = None
    
    # Trade basics
    direction: TradeDirection
    quantity: int
    entry_price: float
    entry_time: datetime
    status: TradeStatus
    
    # Exit info (if closed)
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    realized_pnl: Optional[float] = None
    
    # Rich context
    entry_context: EntryContext
    stop_loss: StopLossConfig
    targets: TargetConfig
    current_state: CurrentTradeState
    sl_recommendation: StopLossRecommendation
    
    # Trade quality metrics
    trade_duration_minutes: Optional[int] = None
    entry_timing_score: Optional[float] = Field(None, description="How good was the entry timing (0-100)")
    
    # Tags and notes
    strategy_name: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class TradeAnalyticsSummary(BaseModel):
    """Summary of all active trades with analytics."""
    
    total_trades: int
    total_unrealized_pnl: float
    total_realized_pnl: float
    
    # Aggregate Greeks
    net_delta: float = 0
    net_theta: float = 0
    net_vega: float = 0
    
    # Risk metrics
    total_risk_if_sl_hit: float = Field(description="Total loss if all SLs hit")
    max_single_trade_risk: float
    portfolio_heat: float = Field(description="% of capital at risk")
    
    # Trades
    trades: List[TradeAnalytics]


# =============================================================================
# Request Models
# =============================================================================

class SetStopLossRequest(BaseModel):
    """Request to set/update stop loss."""
    
    symbol: str
    sl_type: StopLossType
    sl_price: Optional[float] = None
    sl_percentage: Optional[float] = None
    trailing_distance: Optional[float] = None
    trailing_trigger_price: Optional[float] = None


class SetTargetRequest(BaseModel):
    """Request to set/update target."""
    
    symbol: str
    target_price: Optional[float] = None
    target_percentage: Optional[float] = None
    partial_targets: Optional[List[Dict[str, float]]] = None
